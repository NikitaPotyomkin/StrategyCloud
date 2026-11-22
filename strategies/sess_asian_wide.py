"""Strategy: sess_asian_wide (H1).

Idea: Широкая азиатская сессия — fade на открытии Лондона.
Вход: диапазон Азии > p70 → разворот на London open.
Выход: середина азиатского диапазона.
Отличие: wide Asian range часто разворачивается на London open.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_sess_asian_wide(df, period=20):
    """Wide Asian range fade on London open.
    
    Detects wide Asian range (>p70).
    Fade at London open → signal opposite to Asian range.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Calculate Asian range (first 4 bars as proxy)
        asian_high = np.max(highs[:4])
        asian_low = np.min(lows[:4])
        asian_range = asian_high - asian_low
        
        # Calculate average range (proper average of individual bar ranges)
        avg_range = np.mean([highs[j] - lows[j] for j in range(4, len(highs))]) if len(highs) > 4 else 0
        
        # Wide range (>1.5× average)
        if asian_range > 1.5 * avg_range and avg_range > 0:
            # Fade: if price at top of range → short
            if closes[-1] > asian_high * 0.999:
                k[i] = -1
            # If price at bottom of range → long
            elif closes[-1] < asian_low * 1.001:
                k[i] = 1
    
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
    return run_backtest(df, calc_sess_asian_wide, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
