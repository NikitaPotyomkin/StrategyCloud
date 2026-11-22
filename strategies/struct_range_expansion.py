"""Structural: Range Expansion (H1).

Idea: 0134 struct_range_expansion
Вход: выход из 20-барного ренжа по объёму;
      выход: удвоение ренжа.
Отличие: range expansion = пробой консолидации на повышенном объёме.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_range_expansion(df, period=20):
    high_range = df['high'].rolling(period).max().shift(1)
    low_range = df['low'].rolling(period).min().shift(1)
    range_size = high_range - low_range

    # Объём p70
    vol_p70 = df['volume'].rolling(period).quantile(0.70)

    # Пробой ренжа на повышенном объёме
    breakout_up = (df['close'] > high_range) & (df['volume'] > vol_p70)
    breakout_down = (df['close'] < low_range) & (df['volume'] > vol_p70)

    k = np.zeros(len(df))
    k[breakout_up] = 1
    k[breakout_down] = -1

    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Returns 'long' / 'short' / None for engine run_backtest
    if prev == 0 and curr == 1:
        return 'long'
    if prev == 0 and curr == -1:
        return 'short'
    return None


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    return run_backtest(df, calc_struct_range_expansion, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
