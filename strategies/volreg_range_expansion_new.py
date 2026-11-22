"""Strategy: volreg_range_expansion_new (H1).

Idea: today range / 5-барный средний range > 1.6 — расширение диапазона.
Вход: range expansion → signal.
Выход: trail 1.5×ATR.
Отличие: range expansion detection.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_volreg_range_expansion_new(df, period=20):
    """Range expansion detection.
    
    Today range / 5-bar avg > 1.6 → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Today range
        today_range = highs[-1] - lows[-1]
        
        # 5-bar average range
        avg_range = np.mean([highs[j] - lows[j] for j in range(-5, 0)])
        
        # Expansion
        if avg_range > 0 and today_range > 1.6 * avg_range:
            if closes[-1] > closes[-2]:
                k[i] = 1
            else:
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
    return run_backtest(df, calc_volreg_range_expansion_new, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
