"""Strategy: pattern_island_reversal (H1).

Idea: Island reversal (гэпы с обеих сторон) — островной разворот.
Вход: island formed → signal.
Выход: close gaps.
Отличие: island reversal pattern.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pattern_island_reversal(df, period=20):
    """Island reversal detection.
    
    Island (gaps on both sides) → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        opens = df['open'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Detect gaps
        gaps_up = []
        gaps_down = []
        
        for j in range(1, len(opens)):
            if opens[j] > closes[j-1] * 1.001:  # Up gap
                gaps_up.append(j)
            elif opens[j] < closes[j-1] * 0.999:  # Down gap
                gaps_down.append(j)
        
        # Island: gap up then gap down (or vice versa)
        if len(gaps_up) > 0 and len(gaps_down) > 0:
            if gaps_up[-1] == len(opens) - 2 and gaps_down[-1] == len(opens) - 1:
                k[i] = -1  # Island top → short
            elif gaps_down[-1] == len(opens) - 2 and gaps_up[-1] == len(opens) - 1:
                k[i] = 1  # Island bottom → long
    
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
    return run_backtest(df, calc_pattern_island_reversal, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
