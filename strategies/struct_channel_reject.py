"""Strategy: struct_channel_reject (H1).

Idea: Третий отбой от границы наклонного канала — channel reject.
Вход: 3rd rejection → signal.
Выход: 2×ATR.
Отличие: inclined channel rejection.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_channel_reject(df, period=20):
    """Inclined channel rejection.
    
    Third rejection from channel boundary → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Channel boundaries (OLS)
        x = np.arange(period, dtype=float)
        
        # Upper channel
        coeffs_high = np.polyfit(x, highs, 1)
        upper = np.polyval(coeffs_high, period - 1)
        
        # Lower channel
        coeffs_low = np.polyfit(x, lows, 1)
        lower = np.polyval(coeffs_low, period - 1)
        
        # Rejection
        if closes[-1] > upper * 0.99 and closes[-1] < upper:
            k[i] = -1  # Reject upper
        elif closes[-1] < lower * 1.01 and closes[-1] > lower:
            k[i] = 1  # Reject lower
    
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
    return run_backtest(df, calc_struct_channel_reject, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
