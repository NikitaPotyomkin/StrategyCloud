"""Strategy: pattern_wedge_rising (H1).

Idea: Растущий клин — сужающийся канал вверх, слабость тренда.
Вход: пробой нижней границы клина → short.
Выход: высота клина.
Отличие: клин — разворотная фигура, пробой в направлении сужения.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pattern_wedge_rising(df, period=20):
    """Rising wedge detection and breakdown.
    
    Detects rising wedge (higher highs + higher lows, converging).
    Breakdown of lower boundary → short signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        x = np.arange(period, dtype=float)
        
        # Fit upper line (highs)
        try:
            coeffs_high = np.polyfit(x, highs, 1)
            slope_high = coeffs_high[0]
            
            # Fit lower line (lows)
            coeffs_low = np.polyfit(x, lows, 1)
            slope_low = coeffs_low[0]
            
            # Rising wedge: both slopes positive, converging
            if slope_high > 0 and slope_low > 0 and slope_low > slope_high:
                # Check for breakdown
                if closes[-1] < np.polyval(coeffs_low, period - 1):
                    k[i] = -1
        except Exception:
            pass
        
        # Check for falling wedge (bullish)
        try:
            coeffs_high2 = np.polyfit(x, highs, 1)
            slope_high2 = coeffs_high2[0]
            
            coeffs_low2 = np.polyfit(x, lows, 1)
            slope_low2 = coeffs_low2[0]
            
            # Falling wedge: both slopes negative, converging
            if slope_high2 < 0 and slope_low2 < 0 and slope_high2 < slope_low2:
                # Check for breakout
                if closes[-1] > np.polyval(coeffs_high2, period - 1):
                    k[i] = 1
        except Exception:
            pass
    
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
    return run_backtest(df, calc_pattern_wedge_rising, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
