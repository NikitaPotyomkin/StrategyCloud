"""Strategy: struct_prev_day_mid (H1).

Idea: Удержание выше середины прошлого дня — prev day mid hold.
Вход: hold above prev day mid → signal.
Выход: prev day high.
Отличие: prev day midpoint as support.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_prev_day_mid(df, period=20):
    """Previous day midpoint hold.
    
    Hold above prev day mid → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Prev day mid (proxy: mid of previous bars)
        prev_high = np.max(highs[:-1])
        prev_low = np.min(lows[:-1])
        prev_mid = (prev_high + prev_low) / 2
        
        # Hold above
        if closes[-1] > prev_mid:
            k[i] = 1
        elif closes[-1] < prev_mid:
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
    return run_backtest(df, calc_struct_prev_day_mid, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
