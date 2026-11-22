"""Strategy: struct_open_range_break (H1).

Idea: Пробой диапазона первых 3 баров — open range break.
Вход: breakout first 3 bars range → signal.
Выход: 2× range.
Отличие: open range breakout.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_open_range_break(df, period=20):
    """Open range breakout.
    
    Breakout of first 3 bars range → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # First 3 bars range
        range_high = np.max(highs[:3])
        range_low = np.min(lows[:3])
        
        # Breakout
        if closes[-1] > range_high:
            k[i] = 1
        elif closes[-1] < range_low:
            k[i] = -1
    
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
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
    return run_backtest(df, calc_struct_open_range_break, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
