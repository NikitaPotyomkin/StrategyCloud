"""Structural: Swing Break of Structure (H1).

Idea: 0121 struct_swing_bos
Вход: пробой последнего swing-high (Break of Structure);
      выход: следующий swing-low.
Отличие: BOS = структурный пробой, подтверждающий смену тренда.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 5-15 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_swing_bos(df, period=10):
    high_period = df['high'].rolling(period).max().shift(1)
    low_period = df['low'].rolling(period).min().shift(1)

    # Break of Structure
    k = np.zeros(len(df))
    k[df['close'] > high_period] = 1
    k[df['close'] < low_period] = -1

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
    return run_backtest(df, calc_struct_swing_bos, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
