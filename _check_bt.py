#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Прогон ВСЕХ стратегий реестра на синтетических данных: кто падает.

Эмулирует wiring ночного бэктеста: registry_backtest(...) со СКАЛЯРНЫМИ
sl/tp — ровно так, как это делает generic-цикл в functions.py. Исключение
по стратегии = в ночи она молча даст profit 0: его глотает _safe_backtest
и подставляет (0, 0, []). Такая стратегия никогда не попадёт в план, а в
Roadmap будет выглядеть «посчитанной».

Причина №1, которую этот скрипт ловит: модуль написан под список
(`sl = sl_points[0]`), а контракт реестра — скаляр (`sl_dist = sl_points
* point`). Отсюда TypeError на первом же баре.

Запуск из папки StrategyCloud:
    .venv\\Scripts\\python.exe _check_bt.py

Ничего не торгует, ничего не пишет — считает на случайном ряду.
"""
import sys

import numpy as np
import pandas as pd

from strategies._registry import REGISTRY, ENABLED_BATCH, registry_backtest

N_BARS = 400
SL_POINTS, TP_POINTS = 300, 600
POINT, TICK_VALUE, TICK_SIZE = 0.0001, 1.0, 0.0001


# Волатильность намеренно «широкая»: при сигме 0.0005 бар выходил ~2 пункта,
# а SL 300 пунктов за 50 баров не достигался — тогда ЛЮБАЯ стратегия даёт
# 0 сделок, и список «0 сделок» ничего не значит.
def _frame():
    idx = pd.date_range('2026-09-01', periods=N_BARS, freq='h')
    rng = np.random.default_rng(12345)
    close = 1.1000 + np.cumsum(rng.normal(0, 0.0020, N_BARS))
    return pd.DataFrame({
        'time': idx,
        'open': close, 'high': close + 0.0010,
        'low': close - 0.0010, 'close': close,
        'volume': rng.integers(50, 200, N_BARS).astype(float),
    })


def main():
    df = _frame()
    keys = [k for k in ENABLED_BATCH if k in REGISTRY]
    bad, zero, ok = [], [], []

    for key in keys:
        ent = REGISTRY[key]
        params = list(ent.get('grid') or [])
        got = 0
        err = None
        for pk in params:
            try:
                profit, n_trades, _tp = registry_backtest(
                    key, df, pk, SL_POINTS, TP_POINTS,
                    POINT, TICK_VALUE, TICK_SIZE, spread_points=10)
            except Exception as exc:                     # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"
                break
            got += int(n_trades or 0)
        if err:
            bad.append((key, err))
        elif got == 0:
            zero.append(key)
        else:
            ok.append((key, got))

    print(f"реестр в батче: {len(keys)} | считают: {len(ok)} | "
          f"ПАДАЮТ: {len(bad)} | 0 сделок: {len(zero)}")
    print()

    if bad:
        print('=== ПАДАЮТ (в ночи profit = 0) ===')
        for key, err in bad:
            print(f"  {key:32s} {err[:110]}")
        print()

    if zero:
        print('=== НЕ ПАДАЮТ, но 0 сделок на случайном ряду (сигнал редкий) ===')
        for key in zero:
            print(f"  {key}")
        print()

    print('=== топ по числу сделок (проверка, что движок живой) ===')
    for key, n in sorted(ok, key=lambda x: -x[1])[:10]:
        print(f"  {key:32s} {n}")
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
