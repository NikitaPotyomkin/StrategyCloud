"""Strategy: anom_spread_blowout (H1).

Idea: Spread > 3× median — спред аномалия.
Вход: spread blowout → signal.
Выход: 5 баров.
Отличие: spread anomaly detection.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_anom_spread_blowout(df, period=20):
    """Spread blowout anomaly detection.
    
    Spread > 3× median → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # Daily range as spread proxy
        daily_range = np.max(highs) - np.min(lows)
        
        # Median range
        ranges = []
        for j in range(max(0, i-50), i):
            r = df['high'].iloc[j] - df['low'].iloc[j]
            ranges.append(r)
        
        if len(ranges) > 0:
            median_range = np.median(ranges)
            
            # Blowout
            if daily_range > 3 * median_range:
                if df['close'].iloc[i] > df['open'].iloc[i]:
                    k[i] = 1
                else:
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
    return run_backtest(df, calc_anom_spread_blowout, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
