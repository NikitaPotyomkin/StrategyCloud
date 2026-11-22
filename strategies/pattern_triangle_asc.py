"""Strategy: pattern_triangle_asc (H1).

Idea: Восходящий треугольник — горизонтальное сопротивление + растущие минимумы.
Вход: пробой горизонтали вверх → long.
Выход: высота треугольника.
Отличие: геометрическая фигура с формальным детектом.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pattern_triangle_asc(df, period=20):
    """Ascending triangle detection and breakout.
    
    Detects ascending triangle (flat resistance + higher lows).
    Breakout above resistance → long signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Find resistance (flat high)
        high_mean = np.mean(highs[-5:])
        high_std = np.std(highs[-5:])
        
        # Check if highs are relatively flat (resistance)
        if high_std < 0.002 * high_mean:
            # Check for higher lows
            higher_lows = True
            for j in range(2, len(lows)):
                if lows[j] <= lows[j-1]:
                    higher_lows = False
                    break
            
            if higher_lows and closes[-1] > high_mean:
                k[i] = 1
        
        # Check for descending triangle (bearish)
        low_mean = np.mean(lows[-5:])
        low_std = np.std(lows[-5:])
        
        if low_std < 0.002 * low_mean:
            lower_highs = True
            for j in range(2, len(highs)):
                if highs[j] >= highs[j-1]:
                    lower_highs = False
                    break
            
            if lower_highs and closes[-1] < low_mean:
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
    return run_backtest(df, calc_pattern_triangle_asc, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
