"""Strategy: struct_equal_lows (H1).

Idea: Два равных минимума (double bottom) и пробой.
Вход: 2 равных low (в пределах 0.05×ATR) → пробой high между ними → long.
Выход: trail 1.5×ATR или пробой low.
Отличие: equal lows — сильный уровень поддержки, пробой подтверждает силу.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_equal_lows(df, period=20):
    """Two equal lows detection and breakout.
    
    Detects two lows within 0.05×ATR tolerance, then breakout above midpoint high.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        lows = df['low'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_mean = atr.rolling(20).mean().iloc[i]
        tol = 0.05 * atr_mean if atr_mean > 0 else 0.01
        
        # Find two equal lows
        equal_found = False
        for j in range(len(lows) - 2):
            for m in range(j + 2, len(lows)):
                if abs(lows[j] - lows[m]) < tol:
                    # Check if price breaks above high between them
                    mid_high = max(highs[j:m+1])
                    if closes[-1] > mid_high:
                        equal_found = True
                        break
            if equal_found:
                break
        
        if equal_found:
            k[i] = 1
        else:
            # Check for equal highs (bearish)
            equal_highs_found = False
            for j in range(len(highs) - 2):
                for m in range(j + 2, len(highs)):
                    if abs(highs[j] - highs[m]) < tol:
                        mid_low = min(lows[j:m+1])
                        if closes[-1] < mid_low:
                            equal_highs_found = True
                            break
                if equal_highs_found:
                    break
            
            if equal_highs_found:
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
    return run_backtest(df, calc_struct_equal_lows, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
