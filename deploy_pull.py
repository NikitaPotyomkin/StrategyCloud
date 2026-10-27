"""Автодеплой StrategyCloud: pull из репозитория → проверка компиляции → рестарт бота.

Зачем: не бегать до боевой машины. На тестовой делаешь `git push`, а боевая
сама (раз в N минут по планировщику) забирает изменения, ПРОВЕРЯЕТ синтаксис и
перезапускает main.py. Если код битый — откат и НЕ перезапускаем.

Запуск на БОЕВОЙ машине (Windows):
    python deploy_pull.py                # один цикл деплоя (так его зовёт планировщик)
    python deploy_pull.py --check        # только показать, что нового; ничего не менять
    python deploy_pull.py --force        # деплоить даже если идёт полный пересчёт
    python deploy_pull.py --no-restart   # подтянуть файлы, но бота не трогать
    python deploy_pull.py --mode copy    # без git: копировать *.py из сетевой папки

Как настроить планировщик (один раз, на боевой):
    schtasks /Create /SC MINUTE /MO 5 /TN "StrategyCloud deploy" ^
      /TR "\"<python.exe>\" \"C:\\Users\\nikit\\PycharmProjects\\StrategyCloud\\deploy_pull.py\"" ^
      /RL HIGHEST /F
    (путь к python — из твоего venv, напр. ...\\MT5 FX Technologies\\.venv\\Scripts\\python.exe)

Что он пишет:
    journals/deploy.log               — человекочитаемый лог каждого цикла
    checkpoints/deploy_status.json    — последний статус (для дэшборда/проверки)

БЕЗОПАСНОСТЬ (важно):
  * py_compile всех изменённых .py ДО рестарта — битый код не уедет в бой;
  * при ошибке компиляции — git reset --hard на предыдущий коммит (откат);
  * копия старых файлов в MQL5\\Files\\Backup\\StrategyCloud_<ts>\\ на каждый деплой;
  * если идёт полный пересчёт (по маркерам journals/run.log) — деплой ОТКЛАДЫВАЕТСЯ,
    чтобы не убить 2.5–4 часа расчёта. Принудительно: --force.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

# ═══ НАСТРОЙКИ (поправь под боевую машину) ═══════════════════════════════════
# Путь bare-репозитория. На боевой машине он локальный (быстро), тестовая пушит
# в него по UNC: \\192.168.0.106\Users\nikit\PycharmProjects\StrategyCloud.git
REMOTE_GIT = r'C:\Users\nikit\PycharmProjects\StrategyCloud.git'
# Сетевая папка с кодом — для режима --mode copy (если git на боевой не стоит).
REMOTE_COPY = r'\\192.168.0.100\StrategyCloud'   # тестовая машина зашарила папку проекта
BRANCH = 'main'

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, 'journals', 'deploy.log')
STATUS_PATH = os.path.join(HERE, 'checkpoints', 'deploy_status.json')
RUN_LOG = os.path.join(HERE, 'journals', 'run.log')
PY_FILES_MUST_COMPILE = ('main.py', 'functions.py', 'dashboard.py', 'config.py',
                         'trades_db.py', 'trade_log.py', 'backtest_job.py',
                         'peak_trim.py', 'tactic_tilt.py', 'wheel.py',
                         'strategy_engine.py', 'risk_manager.py', 'daily_report.py')

# ═══ ОКНО БЕЗОПАСНОГО РЕСТАРТА ═══
# Бот опрашивает рынок раз в poll_interval (5 с) и принимает решения по ЗАКРЫТИЮ
# баров M5, то есть в :00, :05, :10 ... каждой пятиминутки. Позиции и их SL/TP
# живут на сервере брокера, рестарт их не трогает, но трейл, kill switch и вход
# по новому бару делает процесс: если taskkill попадёт на закрытие бара, этот
# бар будет пропущен. Поэтому рестарт ставим в СЕРЕДИНУ бара: если до закрытия
# осталось меньше BAR_RESTART_GUARD_SEC - ждём середину следующего бара.
BAR_SECONDS = 300            # шаг сигнального таймфрейма (M5 = 300 с)
BAR_RESTART_GUARD_SEC = 90   # минимальный запас до закрытия бара


def wait_for_quiet_window():
    """Сдвигает рестарт в середину M5-бара. Возвращает, сколько секунд ждали."""
    now = time.time()
    to_close = BAR_SECONDS - (now % BAR_SECONDS)   # секунд до закрытия текущего бара
    if to_close > BAR_RESTART_GUARD_SEC:
        return 0.0
    wait = to_close + BAR_SECONDS / 2.0            # ближайшая середина бара
    log(f"рестарт отложен на {wait:.0f} с: до закрытия M5-бара {to_close:.0f} с "
        f"(порог {BAR_RESTART_GUARD_SEC} с) — чтобы не пропустить вход по бару")
    time.sleep(wait)
    return wait
# Маркеры «идёт полный пересчёт» в journals/run.log.
RECALC_START = ('Фоновый ПОЛНЫЙ пересчёт поставлен', '🚀 ПОЛНЫЙ пересчёт поставлен')
RECALC_DONE = ('Фоновый ПОЛНЫЙ пересчёт завершён', '✅ Полный пересчёт завершён')


# ═══ ЛОГИ ════════════════════════════════════════════════════════════════════
def log(msg, quiet=False):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    if not quiet:
        print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def write_status(rec, quiet=False):
    try:
        os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
        with open(STATUS_PATH, 'w', encoding='utf-8') as f:
            json.dump(rec, f, ensure_ascii=False, indent=2, default=str)
    except OSError as exc:
        log(f"WARN: статус не записан: {exc!r}", quiet)


# ═══ GIT ═════════════════════════════════════════════════════════════════════
def git(*args, check=False):
    """Вызов git в папке проекта. Возвращает (rc, stdout+stderr)."""
    try:
        p = subprocess.run(['git', '-C', HERE, *args], capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        return 127, 'git не найден в PATH'
    except subprocess.TimeoutExpired:
        return 124, 'git timeout'
    out = (p.stdout or '') + (p.stderr or '')
    if check and p.returncode != 0:
        log(f"git {' '.join(args)} → rc={p.returncode}: {out.strip()[:400]}")
    return p.returncode, out.strip()


def is_repo():
    return os.path.isdir(os.path.join(HERE, '.git'))


def remote_reachable():
    rc, _ = git('ls-remote', '--exit-code', 'origin', BRANCH)
    return rc == 0


def local_sha():
    rc, out = git('rev-parse', 'HEAD')
    return out.strip() if rc == 0 else ''


def remote_sha():
    rc, out = git('rev-parse', f'origin/{BRANCH}')
    return out.strip() if rc == 0 else ''


def changed_py_files(old_sha, new_sha):
    rc, out = git('diff', '--name-only', old_sha, new_sha)
    if rc != 0:
        return []
    return [ln for ln in out.splitlines() if ln.endswith('.py')]


# ═══ ПРОВЕРКИ ════════════════════════════════════════════════════════════════
def recalc_running():
    """Идёт ли полный пересчёт — по маркерам в хвосте journals/run.log."""
    try:
        with open(RUN_LOG, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[-400:]
    except OSError:
        return False
    last_start = last_done = -1
    for i, ln in enumerate(lines):
        if any(m in ln for m in RECALC_START):
            last_start = i
        if any(m in ln for m in RECALC_DONE):
            last_done = i
    return last_start > last_done >= -1 and last_start >= 0


def compile_gate(files):
    """py_compile изменённых файлов. Возвращает (ok, текст ошибки)."""
    # Компилируем ВСЕ изменённые .py — именно они и уезжают в бой.
    targets = [f for f in files if f.endswith('.py')]
    if not targets:
        return True, ''
    try:
        p = subprocess.run([sys.executable, '-m', 'py_compile', *targets],
                           cwd=HERE, capture_output=True, text=True, timeout=300)
    except Exception as exc:
        return False, f'py_compile не запустился: {exc!r}'
    if p.returncode != 0:
        return False, ((p.stdout or '') + (p.stderr or '')).strip()[:1500]
    return True, ''


def backup_files(files):
    """Копия текущих версий перед деплоем (откат руками, если что)."""
    try:
        dst_root = os.path.join(HERE, 'checkpoints', '_backup')  # git-ignored
        # Бэкап кладём в checkpoints/ (он в .gitignore) — путь не зависит от профиля.
        dst_root = os.path.normpath(dst_root)
    except Exception:
        dst_root = os.path.join(HERE, 'checkpoints', '_backup')
    dst = os.path.join(dst_root, 'StrategyCloud_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    try:
        os.makedirs(dst, exist_ok=True)
        for f in files:
            src = os.path.join(HERE, f)
            if os.path.isfile(src):
                dst_file = os.path.join(dst, f)
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                shutil.copy2(src, dst_file)
        return dst
    except OSError as exc:
        log(f"WARN: бэкап не сделан: {exc!r}")
        return ''


# ═══ ПРОЦЕСС БОТА ════════════════════════════════════════════════════════════
def find_bot_pids():
    """PID процессов python, у которых в командной строке main.py."""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
          "ForEach-Object { \"{0}|{1}\" -f $_.ProcessId, $_.CommandLine }")
    try:
        p = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                           capture_output=True, text=True, timeout=60)
    except Exception:
        return []
    pids = []
    for ln in (p.stdout or '').splitlines():
        if 'main.py' not in ln:
            continue
        pid = ln.split('|', 1)[0].strip()
        if pid.isdigit():
            pids.append(int(pid))
    return pids


def stop_bot():
    pids = find_bot_pids()
    if not pids:
        log("бот не запущен — останавливать нечего")
        return True
    for pid in pids:
        log(f"остановка main.py pid={pid}")
        subprocess.run(['taskkill', '/PID', str(pid)], capture_output=True, text=True)
    for _ in range(10):
        if not find_bot_pids():
            return True
        import time
        time.sleep(1)
    for pid in find_bot_pids():
        log(f"жёсткое убийство pid={pid}")
        subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True, text=True)
    return not find_bot_pids()


def start_bot():
    log(f"запуск: {sys.executable} main.py (cwd={HERE})")
    flags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)
    subprocess.Popen([sys.executable, 'main.py'], cwd=HERE, creationflags=flags,
                     close_fds=True)
    return True


# ═══ ОСНОВНОЙ СЦЕНАРИЙ ═══════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description='Autodeploy StrategyCloud')
    ap.add_argument('--check', action='store_true', help='только показать, что нового')
    ap.add_argument('--force', action='store_true', help='деплоить даже при идущем пересчёте')
    ap.add_argument('--no-restart', action='store_true', help='не перезапускать бота')
    ap.add_argument('--mode', choices=('git', 'copy'), default='git')
    args = ap.parse_args()

    quiet = args.check
    rec = {'ts': datetime.now().isoformat(timespec='seconds'), 'mode': args.mode,
           'ok': True, 'deployed': False, 'restarted': False,
           'from': '', 'to': '', 'files': [], 'error': '', 'note': ''}

    # ── 0. Репозиторий на месте? ──
    if args.mode == 'git' and not is_repo():
        rec.update(ok=False, error='нет .git — первичная настройка не сделана',
                   note=f'git init && git remote add origin {REMOTE_GIT} && '
                        f'git fetch origin && git reset --hard origin/{BRANCH}')
        log('ERROR: папка не git-репозиторий. Первичная настройка: ' + rec['note'])
        write_status(rec, quiet)
        return 2
    if args.mode == 'git' and not remote_reachable():
        rec.update(ok=False, error=f'origin недоступен: {REMOTE_GIT}')
        log(rec['error'] + ' (сеть/шара?) — выходим')
        write_status(rec, quiet)
        return 2

    # ── 1. Что нового? ──
    old = local_sha()
    rec['from'] = old[:8]
    if args.mode == 'git':
        rc, _ = git('fetch', 'origin', BRANCH, '--quiet')
        if rc != 0:
            rec.update(ok=False, error='git fetch не удался')
            log(rec['error'])
            write_status(rec, quiet)
            return 2
        new = remote_sha()
    else:
        new = ''  # в режиме copy сравниваем по mtime ниже
    rec['to'] = (new or '')[:8]

    if args.mode == 'git' and new and old == new:
        rec['note'] = 'изменений нет'
        log(f"изменений нет (HEAD={old[:8]})", quiet)
        write_status(rec, quiet)
        return 0

    files = changed_py_files(old, new) if (args.mode == 'git' and old and new) else []
    if args.mode == 'copy':
        files = _newer_than_local_copy()
    rec['files'] = files
    if not files:
        rec['note'] = 'менялись не .py файлы — деплой не нужен'
        log(rec['note'], quiet)
        write_status(rec, quiet)
        return 0

    log(f"новые/изменённые: {', '.join(files)}", quiet)
    if args.check:
        log('режим --check: ничего не меняю', quiet)
        write_status(rec, quiet)
        return 0

    # ── 2. Не мешаем полному пересчёту ──
    if recalc_running() and not args.force:
        rec['note'] = 'идёт полный пересчёт — деплой отложен (--force чтобы всё равно)'
        log(rec['note'], quiet)
        write_status(rec, quiet)
        return 3

    # ── 3. Бэкап + обновление файлов ──
    bdir = backup_files(files)
    if bdir:
        log(f"бэкап: {bdir}")
    if args.mode == 'git':
        rc, out = git('reset', '--hard', f'origin/{BRANCH}')
        if rc != 0:
            rec.update(ok=False, error=f'git reset не удался: {out[:300]}')
            log(rec['error'])
            write_status(rec, quiet)
            return 2
        log(f"файлы обновлены до {new[:8]}")
    else:
        if not _copy_from_share(files):
            rec.update(ok=False, error='копирование из сетевой папки не удалось')
            log(rec['error'])
            write_status(rec, quiet)
            return 2

    # ── 4. Гейт компиляции ──
    ok, err = compile_gate(files)
    if not ok:
        log('❌ py_compile упал — откатываю ' + (('на ' + old[:8]) if old else 'вручную из бэкапа'))
        log(err)
        if args.mode == 'git' and old:
            git('reset', '--hard', old)
        rec.update(ok=False, deployed=False, error='py_compile: ' + err[:800])
        write_status(rec, quiet)
        return 4
    log('✅ py_compile чистый')
    rec['deployed'] = True

    # ── 5. Рестарт ──
    if args.no_restart:
        rec['note'] = 'файлы обновлены, рестарт отключён (--no-restart)'
        log(rec['note'])
        write_status(rec, quiet)
        return 0
    _waited = wait_for_quiet_window()
    if _waited:
        rec['note'] = ((rec['note'] + ' · ') if rec['note'] else '') + \
                      f'рестарт сдвинут на {_waited:.0f} с (закрытие бара M5)'
    if not stop_bot():
        rec.update(ok=False, error='не удалось остановить main.py')
        log(rec['error'])
        write_status(rec, quiet)
        return 5
    start_bot()
    rec['restarted'] = True
    log('боевой бот перезапущен с новым кодом')
    write_status(rec, quiet)
    return 0


COPY_SKIP_DIRS = {'.venv', 'venv', '__pycache__', '.git', '.idea', 'checkpoints', 'journals', '.streamlit'}


def _sha1(path):
    """SHA1 файла — чтобы сравнивать содержимое, а не время правки."""
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _walk_py(root):
    """Все *.py под root рекурсивно, кроме служебных папок. Пути относительно root."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in COPY_SKIP_DIRS]
        for fname in filenames:
            if fname.endswith('.py'):
                out.append(os.path.relpath(os.path.join(dirpath, fname), root))
    return out


def _diff_needs_copy(src, dst):
    """True, если локального файла нет или содержимое отличается."""
    if not os.path.isfile(dst):
        return True
    if os.path.getsize(src) != os.path.getsize(dst):
        return True
    return _sha1(src) != _sha1(dst)


def _newer_than_local_copy():
    """Режим copy: какие *.py отличаются от сетевой копии (рекурсивно, по содержимому)."""
    out = []
    try:
        for name in _walk_py(REMOTE_COPY):
            if not name.endswith('.py'):
                continue
            src = os.path.join(REMOTE_COPY, name)
            dst = os.path.join(HERE, name)
            if not os.path.isfile(src):
                continue
            if _diff_needs_copy(src, dst):
                out.append(name)
    except OSError as exc:
        log(f"WARN: сетевая папка недоступна: {exc!r}")
    return out


def _copy_from_share(files):
    try:
        for name in files:
            dst = os.path.join(HERE, name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(REMOTE_COPY, name), dst)
        return True
    except OSError as exc:
        log(f"ERROR копирования: {exc!r}")
        return False


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # никакой сбой деплоя не должен ронять планировщик
        log(f"FATAL: {exc!r}")
        write_status({'ts': datetime.now().isoformat(timespec='seconds'),
                      'ok': False, 'error': repr(exc)})
        sys.exit(1)
