"""Strategy: pattern_double_bottom_w (H1).

Idea: Двойное дно (W-bottom) — разворотная фигура.
Вход: второе дно выше первого + пробой середины → long.
Выход: высота W.
Отличие: второе дно выше первого усиливает бычий сигнал.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pattern_double_bottom_w(df, period=20):
    """Double bottom (W-pattern) detection.
    
    Detects W-bottom with higher second low.
    Midpoint breakout → long signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # Divide into two halves
        mid = len(lows) // 2
        
        # Find lows in each half
        low1 = np.min(lows[:mid])
        low2 = np.min(lows[mid:])
        
        # Find high between lows (neckline/midpoint)
        neckline = np.max(lows[:mid])
        
        # Check for W-pattern (second low higher than first)
        if low2 > low1 * 1.001 and low2 < low1 * 1.02:
            # Check for neckline breakout
            if closes[-1] > neckline:
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
    return run_backtest(df, calc_pattern_double_bottom_w, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
