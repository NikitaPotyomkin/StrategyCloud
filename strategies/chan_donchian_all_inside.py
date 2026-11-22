"""Strategy: chan_donchian_all_inside (H1).

Idea: 20 баров внутри прошлого канала, пробой — все внутри канала.
Вход: пробой → signal.
Выход: 2× ширина.
Отличие: all-inside Donchian channel breakout.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_chan_donchian_all_inside(df, period=20):
    """Donchian all-inside breakout.
    
    20 bars inside previous channel → breakout signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Previous channel (2× period before current window)
        prev_start = max(0, i - 2 * period)
        prev_highs = df['high'].iloc[prev_start:i-period].values
        prev_lows = df['low'].iloc[prev_start:i-period].values
        
        if len(prev_highs) > 0:
            channel_high = np.max(prev_highs)
            channel_low = np.min(prev_lows)
            
            # All inside
            if np.all(highs < channel_high) and np.all(lows > channel_low):
                # Breakout
                if closes[-1] > channel_high:
                    k[i] = 1
                elif closes[-1] < channel_low:
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
    return run_backtest(df, calc_chan_donchian_all_inside, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
