#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Правка скалярного контракта SL/TP в модулях стратегий реестра.

Причина: эталонный движок (strategies/_bt_core.py) считает
    sl_dist = sl_points * point
то есть ждёт СКАЛЯР. Часть модулей написана под список и делает
    sl = sl_points[0] / tp = tp_points[0]
Под registry_backtest приходит скаляр → TypeError: 'int' object is not
subscriptable → _safe_backtest в functions.py глотает исключение и отдаёт
(0, 0, []) — стратегия молча получает profit 0 и никогда не попадает в план.

Что делает скрипт: в файлах strategies/*.py заменяет
    sl_points[0] → sl_points
    tp_points[0] → tp_points
Только эти два шаблона, ничего больше не трогает. По умолчанию — СУХОЙ
ПРОГОН (только показывает, что изменит). Запись — с флагом --apply.

Запуск из папки StrategyCloud:
    .venv\\Scripts\\python.exe _fix_sl_tp.py            # посмотреть
    .venv\\Scripts\\python.exe _fix_sl_tp.py --apply    # записать

После записи обязательно:
    .venv\\Scripts\\python.exe _check_bt.py             # список ПАДАЮТ должен сократиться
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
STRAT = os.path.join(ROOT, 'strategies')

# Инфраструктура — не стратегии, не трогаем.
INFRA = {'__init__', 'base', '_bt_core', '_calc_cache', '_registry'}

# Исключений нет: osc_klinger / pattern_rectangle_break / pattern_wedge_rising —
# это живые модули ключей реестра klinger / rect_break / wedge_rise
# имя файла и имя ключа просто не совпадают.
SKIP = set()

PAIRS = (('sl_points[0]', 'sl_points'), ('tp_points[0]', 'tp_points'))


def main():
    apply = '--apply' in sys.argv
    rows, total = [], 0

    for fn in sorted(os.listdir(STRAT)):
        if not fn.endswith('.py'):
            continue
        name = fn[:-3]
        if name in SKIP or name in INFRA:
            continue
        path = os.path.join(STRAT, fn)
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                src = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            print(f"  [SKIP] {fn}: не читается ({exc})")
            continue

        new, hits = src, []
        for old, rep in PAIRS:
            n = new.count(old)
            if n:
                hits.append(f"{old} → {rep} ×{n}")
                new = new.replace(old, rep)
        if new == src:
            continue

        rows.append((fn, hits))
        total += 1
        if apply:
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(new)

    for fn, hits in rows:
        print(f"  {fn:34s} {'; '.join(hits)}")

    print()
    print(f"файлов к правке: {total} | режим: {'ЗАПИСЬ' if apply else 'сухой прогон'}")
    if total and not apply:
        print("ничего не изменено — повтори с --apply")
    return 0


if __name__ == '__main__':
    sys.exit(main())
