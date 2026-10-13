"""Vortex Indicator crossover, каталог #34.

Сигнал: VI+ пересекает VI− сверху (LONG) или снизу (SHORT).
Standalone-модуль: не подключён к main/dispatcher.
Колонка 'k' — разность (VI+ − VI−), value-cross нуля.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest


def calc_vortex(df, period):
    """period — окно суммирования. Колонка 'k' = VI+ − VI−."""
    prev_high = df['high'].shift(1)
    prev_low = df['low'].shift(1)
    prev_close = df['close'].shift(1)

    vm_plus = (df['high'] - prev_low).abs()
    vm_minus = (df['low'] - prev_high).abs()
    tr = pd.concat([df['high'] - df['low'],
                    (df['high'] - prev_close).abs(),
                    (df['low'] - prev_close).abs()], axis=1).max(axis=1)

    tr_sum = tr.rolling(period, min_periods=period).sum().replace(0.0, np.nan)
    vi_plus = vm_plus.rolling(period, min_periods=period).sum() / tr_sum
    vi_minus = vm_minus.rolling(period, min_periods=period).sum() / tr_sum
    df = df.copy()
    df['k'] = (vi_plus - vi_minus).fillna(0.0)
    return df


def check_entry(prev_k, curr_k):
    if prev_k <= 0 < curr_k:
        return 'long'
    if prev_k >= 0 > curr_k:
        return 'short'
    return None


def check_exit(prev_k, curr_k, direction):
    if direction == 'long':
        return prev_k >= 0 > curr_k
    return prev_k <= 0 < curr_k


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_vortex, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
