"""Strategy: struct_choch (H1).

Idea: Change of Character (CHoCH) — смена характера тренда.
Вход: серия LL затем пробой последнего HH → long; серия HH затем пробой последнего LL → short.
Выход: противоположная смена структуры.
Отличие: CHoCH фиксирует смену структуры до движения, а не после пробоя.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_choch(df, period=20):
    """Change of Character detection.
    
    Detects series of lower lows then break of last higher high (bullish CHoCH),
    or series of higher highs then break of last lower low (bearish CHoCH).
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Find recent swing points
        # Look for lower lows sequence
        ll_count = 0
        for j in range(2, len(lows)):
            if lows[j] < lows[j-1]:
                ll_count += 1
            else:
                ll_count = 0
        
        # Look for higher highs sequence
        hh_count = 0
        for j in range(2, len(highs)):
            if highs[j] > highs[j-1]:
                hh_count += 1
            else:
                hh_count = 0
        
        # Bullish CHoCH: enough lower lows then break above last high
        if ll_count >= 2 and closes[-1] > highs[-2]:
            k[i] = 1
        # Bearish CHoCH: enough higher highs then break below last low
        elif hh_count >= 2 and closes[-1] < lows[-2]:
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
    return run_backtest(df, calc_struct_choch, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
