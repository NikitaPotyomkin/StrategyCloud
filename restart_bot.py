"""Перезапуск боевого бота на машине, где он крутится.

Зачем: кнопка `deploy.bat` запускается на рабочей машине, а перезапустить main.py
нужно на боевой. Эта обёртка — единственное, что дёргает задача планировщика
"StrategyCloud restart". Вся механика (поиск процессов, останов, старт, py_compile)
живёт в deploy_pull.py — здесь только последовательность, чтобы не плодить второй
экземпляр бота и не проверять синтаксис дважды.

Порядок (важен именно такой):
    1) py_compile всех боевых .py — битый код НЕ уедет в бой, старый процесс живёт;
    2) остановка текущего main.py (иначе два бота = дубли ордеров и конфликт по trades.db);
    3) старт main.py в собственном окне консоли.

Запуск (на боевой машине):
    python restart_bot.py              # проверка + перезапуск
    python restart_bot.py --no-start   # только остановить
    python restart_bot.py --check      # только py_compile, бота не трогать

Возвращает 0 при успехе, 1 если проверка/останов не удались.
"""

import os
import sys

import deploy_pull as dp


def main():
    no_start = '--no-start' in sys.argv
    check_only = '--check' in sys.argv

    # ── 1. Гейт: синтаксис всех боевых файлов ДО остановки бота ──
    files = [name for name in dp.PY_FILES_MUST_COMPILE
             if os.path.exists(os.path.join(dp.HERE, name))]
    ok, err = dp.compile_gate(files)
    if not ok:
        print(f"[ERROR] py_compile не прошёл — бот НЕ перезапускаю (старый код жив): {err}")
        return 1
    print(f"[RESTART] py_compile: OK ({len(files)} файлов)")
    if check_only:
        return 0

    # ── 2. Остановка текущего бота ──
    pids = dp.find_bot_pids()
    print(f"[RESTART] процессов main.py найдено: {pids if pids else 'нет'}")
    if pids and not dp.stop_bot():
        print("[ERROR] не удалось остановить main.py — новый не запускаю "
              "(два экземпляра торговать не должны)")
        return 1
    if no_start:
        return 0

    # ── 3. Старт ──
    dp.start_bot()
    print("[RESTART] main.py запущен в новом окне консоли")
    return 0


if __name__ == '__main__':
    sys.exit(main())
