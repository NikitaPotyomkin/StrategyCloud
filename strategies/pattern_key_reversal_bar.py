"""Strategy: pattern_key_reversal_bar (H1).

Idea: Bar с диапазоном > 2×ATR на экстремуме 20 баров — key reversal.
Вход: key reversal → signal.
Выход: 2×ATR.
Отличие: key reversal bar detection.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pattern_key_reversal_bar(df, period=20):
    """Key reversal bar detection.
    
    Range > 2×ATR at 20-bar extreme → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        opens = df['open'].iloc[i-period:i].values
        
        # ATR
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_mean = atr.rolling(20).mean().iloc[i]
        
        # Range
        today_range = highs[-1] - lows[-1]
        
        # Key reversal
        if today_range > 2 * atr_mean:
            # At extreme
            if highs[-1] == np.max(highs) and closes[-1] < opens[-1]:
                k[i] = -1  # Key reversal top
            elif lows[-1] == np.min(lows) and closes[-1] > opens[-1]:
                k[i] = 1  # Key reversal bottom
    
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
    return run_backtest(df, calc_pattern_key_reversal_bar, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
