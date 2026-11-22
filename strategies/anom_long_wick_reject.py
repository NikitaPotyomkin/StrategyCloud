"""Strategy: anom_long_wick_reject (H1).

Idea: Long wick rejection — длинная тень.
Вход: wick > 2× body → signal.
Выход: 2×ATR.
Отличие: wick rejection anomaly.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_anom_long_wick_reject(df, period=20):
    """Long wick rejection detection.
    
    Wick > 2× body → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        opens = df['open'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # Body and wick
        body = abs(closes[-1] - opens[-1])
        upper_wick = highs[-1] - max(opens[-1], closes[-1])
        lower_wick = min(opens[-1], closes[-1]) - lows[-1]
        
        # Long wick rejection
        if body > 0:
            if upper_wick > 2 * body:
                k[i] = -1  # Upper wick rejection
            elif lower_wick > 2 * body:
                k[i] = 1  # Lower wick rejection
    
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
    return run_backtest(df, calc_anom_long_wick_reject, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
