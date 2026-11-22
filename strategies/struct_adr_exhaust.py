"""Strategy: struct_adr_exhaust (H1).

Idea: Пройдено > 85% среднего дневного диапазона — ADR exhaustion.
Вход: > 85% ADR → fade.
Выход: ADR.
Отличие: ADR exhaustion mean reversion.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_adr_exhaust(df, period=20):
    """ADR exhaustion detection.
    
    > 85% ADR passed → fade signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        opens = df['open'].iloc[i-period:i].values
        
        # Today range
        today_range = np.max(highs) - np.min(lows)
        
        # ADR (average daily range)
        adr = df['high'].rolling(20).max() - df['low'].rolling(20).min()
        adr_mean = adr.rolling(20).mean().iloc[i]
        
        # Exhaustion > 85% ADR
        if adr_mean > 0 and today_range > 0.85 * adr_mean:
            # Fade
            if opens[-1] < closes[-1]:
                k[i] = -1  # Up move exhausted → short
            else:
                k[i] = 1  # Down move exhausted → long
    
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
    return run_backtest(df, calc_struct_adr_exhaust, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
