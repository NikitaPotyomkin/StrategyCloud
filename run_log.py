"""Логирование прогонов StrategyCloud в journals/run.log.

Зачем: все print() в пайплайне уходят только в stdout. Если прогон запускает
Планировщик задач без редиректа, вывод [WHEEL] / [STEERING] исчезает навсегда.
Здесь stdout и stderr дублируются в файл с ротацией, поэтому консольная картина
ночного прогона (включая трейсбеки) остаётся на диске.

Подключение — одна строка в начале main.py:

    try:
        import run_log
        run_log.setup()
    except Exception:
        pass

Модуль намеренно fail-safe: любая ошибка настройки глушится, прогон из-за лога
не падает. Повторный setup() ничего не делает.
"""
import logging
import os
import shutil
import sys
import time
from datetime import datetime

from logging.handlers import RotatingFileHandler

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'journals')
_LOG_FILE = os.path.join(_LOG_DIR, 'run.log')
_MAX_BYTES = 2 * 1024 * 1024
_BACKUPS = 3

_configured = False
_logger = logging.getLogger('strategycloud.run')


class _Tee:
    """Обёртка потока: пишет и в исходный поток, и в логгер.

    Нужна потому, что пайплайн печатает через print(), а не через logging.
    """

    def __init__(self, stream, logger, level=logging.INFO):
        self._stream = stream
        self._logger = logger
        self._level = level

    def write(self, data):
        if self._stream is not None:
            try:
                self._stream.write(data)
            except Exception:
                pass
        if data:
            text = data.rstrip('\n')
            if text.strip():
                try:
                    self._logger.log(self._level, text)
                except Exception:
                    pass
        return len(data) if data else 0

    def flush(self):
        if self._stream is not None:
            try:
                self._stream.flush()
            except Exception:
                pass

    def isatty(self):
        return False

    def fileno(self):
        # mt5/библиотеки могут звать fileno() — пробрасываем в реальный поток.
        if self._stream is not None and hasattr(self._stream, 'fileno'):
            return self._stream.fileno()
        raise OSError('no fileno')


class _SafeRotatingFileHandler(RotatingFileHandler):
    """Ротация, которая не сыпет «--- Logging error ---» и не теряет лог.

    На Windows os.rename() в ротации падает с WinError 32 («файл занят другим
    процессом»), если journals/run.log держит кто-то ещё: второй экземпляр бота,
    открытый просмотрщик/редактор лога, антивирус или облачная синхронизация.
    Штатный logging в этом случае на КАЖДУЮ запись печатает трейсбек в stderr,
    а stderr у нас через _Tee уходит обратно в логгер — получается шторм
    «--- Logging error ---» и потеря самих сообщений прогона.

    Что делаем вместо этого:
      • rotate() при ошибке не падает: копирует лог в бэкап (copyfile) и усекает
        исходный файл. Держатель файла запрещает переименование, но обычно не
        запись — поэтому лог продолжает работать;
      • если не вышло и это — ротация откладывается на _RETRY_SEC, сообщения
        продолжают писаться в текущий файл (он растёт, но пишется);
      • handleError() печатает причину ОДИН раз в _ERR_INTERVAL_SEC и только в
        настоящий stderr (sys.__stderr__), без трейсбека и без рекурсии в _Tee.
    """

    _ERR_INTERVAL_SEC = 600.0     # как часто жалуемся в stderr
    _RETRY_SEC = 900.0            # пауза перед следующей попыткой ротации

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._err_last = 0.0
        self._err_kind = ''
        self._blocked_until = 0.0

    def rotate(self, source, dest):
        """Переименование, а при WinError 32 — «копия + усечение»."""
        if not os.path.exists(source):
            return
        try:
            super().rotate(source, dest)
            self._blocked_until = 0.0
            return
        except Exception as exc:          # OSError(32/33), а также всё прочее
            err = exc
        try:
            shutil.copyfile(source, dest)
            with open(source, 'w', encoding='utf-8'):
                pass                       # усечение на месте
            self._note(f'ротация копией: {os.path.basename(source)} -> '
                       f'{os.path.basename(dest)} (переименование не удалось: {err!r})')
            return
        except Exception as exc:
            self._blocked_until = time.time() + self._RETRY_SEC
            self._note(f'ротация отложена на {int(self._RETRY_SEC)} с — {err!r}; '
                       f'копия тоже не удалась: {exc!r}. Файл держит другой процесс: '
                       f'закройте просмотр run.log / второй экземпляр бота')
            raise

    def doRollover(self):
        """Штатная ротация, но с паузой до следующей попытки.

        Сбой случается и ДО rotate(): os.remove/os.replace бэкапа (.1 -> .2),
        если занят уже бэкап. Без паузы logging пробовал бы ротацию на КАЖДОЙ
        записи, каждый раз закрывая и переоткрывая файл.
        """
        try:
            super().doRollover()
        except Exception as exc:
            self._blocked_until = time.time() + self._RETRY_SEC
            self._note(f'ротация не удалась: {exc!r}')
            raise

    def shouldRollover(self, record):
        if time.time() < self._blocked_until:
            return False                   # файл занят — не дёргаем ротацию
        return super().shouldRollover(record)

    def handleError(self, record):
        """Без трейсбека: причина печатается один раз в _ERR_INTERVAL_SEC."""
        exc = sys.exc_info()[1]
        kind = f'{type(exc).__name__}: {exc}' if exc is not None else 'unknown'
        now = time.time()
        if kind == self._err_kind and (now - self._err_last) < self._ERR_INTERVAL_SEC:
            return
        self._err_kind = kind
        self._err_last = now
        self._note(f'запись в {os.path.basename(self.baseFilename)} не удалась: {kind}')

    def _note(self, text):
        """Строка в НАСТОЯЩИЙ stderr: минуя _Tee, чтобы не зациклиться."""
        try:
            sys.__stderr__.write(f'[run_log] {text}\n')
            sys.__stderr__.flush()
        except Exception:
            pass


def setup(level=logging.INFO, max_bytes=_MAX_BYTES, backups=_BACKUPS):
    """Включить дублирование stdout/stderr в journals/run.log.

    Идемпотентно и безопасно: исключения наружу не пробрасываются.
    """
    global _configured
    if _configured:
        return _LOG_FILE
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        handler = _SafeRotatingFileHandler(_LOG_FILE, maxBytes=max_bytes,
                                           backupCount=backups,
                                           encoding='utf-8')
        # Ротация с защитой от «файл занят» (см. _SafeRotatingFileHandler):
        # WinError 32 при переименовании больше не роняет запись в лог.
        handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)-5s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'))
        _logger.setLevel(level)
        _logger.propagate = False
        _logger.addHandler(handler)
        # stdout — как INFO, stderr (трейсбеки, warnings) — как ERROR
        sys.stdout = _Tee(sys.__stdout__, _logger, logging.INFO)
        sys.stderr = _Tee(sys.__stderr__, _logger, logging.ERROR)
        _configured = True
        _logger.info('=== START %s | cwd=%s | argv=%s ===',
                     datetime.now().isoformat(timespec='seconds'),
                     os.getcwd(), sys.argv)
    except Exception:
        _configured = False
    return _LOG_FILE


def path():
    """Путь к файлу лога (для сообщений и дэшборда)."""
    return _LOG_FILE


def is_active():
    """True, если логирование включено."""
    return _configured
