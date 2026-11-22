"""Strategy: pattern_pennant (H1).

Idea: Вымпел (pennant) — сужающийся канал после импульса.
Вход: пробой направления импульса → продолжение.
Выход: высота вымпела.
Отличие: pennant — продолжение после быстрого импульса.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pattern_pennant(df, period=20):
    """Pennant detection and breakout.
    
    Detects pennant (converging channel after impulse).
    Breakout in impulse direction → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Calculate range convergence
        ranges = highs - lows
        range_mean = np.mean(ranges)
        range_last = ranges[-1]
        
        # Check for convergence (narrowing range)
        if range_last < 0.5 * range_mean:
            # Check for breakout
            high_max = np.max(highs[:-1])
            low_min = np.min(lows[:-1])
            
            if closes[-1] > high_max:
                k[i] = 1
            elif closes[-1] < low_min:
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
    return run_backtest(df, calc_pattern_pennant, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
