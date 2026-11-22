#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Модули strategies/, которые не участвуют НИ в реестре, НИ в native-сетке.

Это и есть «пробел» из вкладки Roadmap (stat['gap']): файл есть, но в ночном
обсчёте его нет. Скрипт для каждого такого модуля показывает контракт, чтобы
было видно, подключается он к реестру как есть или требует адаптера.

Запуск из папки StrategyCloud:
    .venv\\Scripts\\python.exe _check_gap.py

Ничего не торгует, ничего не пишет — только читает.
"""
import importlib
import inspect
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import roadmap_scan  # noqa: E402  (нужен sys.path выше)


def _contract(mod):
    """(состав контракта, сигнатура backtest) для модуля стратегии."""
    calc = [n for n in dir(mod) if n.startswith('calc_')]
    parts = []
    for slot in ('check_entry', 'check_exit', 'backtest'):
        parts.append(slot if callable(getattr(mod, slot, None)) else '-' + slot)
    parts.append(calc[0] if calc else '-calc_*')

    sig = ''
    bt = getattr(mod, 'backtest', None)
    if callable(bt):
        try:
            sig = str(inspect.signature(bt))
        except (TypeError, ValueError):
            sig = '(?)'
    return ' '.join(parts), sig


def main():
    rows, stat = roadmap_scan.scan()
    mods = sorted((r.get('module') or '').replace('.py', '') for r in rows)
    reg = [r for r in rows if r.get('reg')]
    gap = sorted((r for r in rows
                  if not r.get('infra') and not r.get('reg') and not r.get('native')),
                 key=lambda r: (r.get('module') or ''))

    print(f"файлов .py {stat['files']} | infra {stat['infra']} | "
          f"реестр {len(reg)} | native {stat['native']} | пробел {stat['gap']}")
    print()
    for r in gap:
        name = (r.get('module') or '').replace('.py', '')
        try:
            mod = importlib.import_module(f'strategies.{name}')
            contract, sig = _contract(mod)
        except Exception as exc:                      # noqa: BLE001
            contract, sig = f'ИМПОРТ УПАЛ: {exc!r}', ''
        print(f"{name:36s} {contract}")
        if sig:
            print(f"{'':36s} backtest{sig}")
    print()
    print('Контракт реестра: calc_* / check_entry / check_exit / backtest')
    print('backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,')
    print('         sim_lot=0.01, spread_points=0)  — sl_points и tp_points СКАЛЯРЫ')
    return 0


if __name__ == '__main__':
    sys.exit(main())
