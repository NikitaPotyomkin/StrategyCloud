"""Structural: Liquidity Sweep (H1).

Idea: 0126 struct_liquidity_sweep
Вход: снятие стопов (прокол экстремума + возврат);
      выход: trail 1.5×ATR.
Отличие: liquidity sweep = цена пробивает уровень, но закрывается обратно в диапазон.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 4-12 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_liquidity_sweep(df, period=20):
    high_20 = df['high'].rolling(period).max()
    low_20 = df['low'].rolling(period).min()

    # Пробой + возврат
    broke_high = df['high'] > high_20.shift(1)
    closed_inside = df['close'] < high_20.shift(1)

    broke_low = df['low'] < low_20.shift(1)
    closed_inside_low = df['close'] > low_20.shift(1)

    k = np.zeros(len(df))
    k[broke_high & closed_inside] = -1
    k[broke_low & closed_inside_low] = 1

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
    return run_backtest(df, calc_struct_liquidity_sweep, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
