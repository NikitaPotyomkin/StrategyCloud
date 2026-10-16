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
import sys
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


def setup(level=logging.INFO, max_bytes=_MAX_BYTES, backups=_BACKUPS):
    """Включить дублирование stdout/stderr в journals/run.log.

    Идемпотентно и безопасно: исключения наружу не пробрасываются.
    """
    global _configured
    if _configured:
        return _LOG_FILE
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        handler = RotatingFileHandler(_LOG_FILE, maxBytes=max_bytes,
                                      backupCount=backups, encoding='utf-8')
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
