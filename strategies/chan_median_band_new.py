"""Strategy: chan_median_band (H1).

Idea: Close выше rolling-median + 1.5 MAD — median band.
Вход: breakout median → signal.
Выход: median cross.
Отличие: median band robust to outliers.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_chan_median_band(df, period=20):
    """Median band breakout.
    
    Breakout of rolling median + 1.5 MAD → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Median and MAD
        median = np.median(closes)
        mad = np.mean(np.abs(closes - median))
        
        # Bands
        upper = median + 1.5 * mad
        lower = median - 1.5 * mad
        
        # Breakout
        if closes[-1] > upper:
            k[i] = 1
        elif closes[-1] < lower:
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
    return run_backtest(df, calc_chan_median_band, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
