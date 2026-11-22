"""Strategy: chan_donchian_double (H1).

Idea: Пробой канала(50) после консолидации у канала(10) — двойной Donchian.
Вход: пробой → signal.
Выход: 1.5× ширины.
Отличие: двойной Donchian channel confluence.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_chan_donchian_double(df, period=20):
    """Double Donchian channel confluence.
    
    Breakout of 50-bar channel after 10-bar consolidation → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # 50-bar channel
        channel_high = np.max(highs[-50:]) if len(highs) >= 50 else np.max(highs)
        channel_low = np.min(lows[-50:]) if len(lows) >= 50 else np.min(lows)
        
        # 10-bar consolidation
        cons_high = np.max(highs[-10:])
        cons_low = np.min(lows[-10:])
        
        # Consolidation near channel edge
        if cons_high > channel_high * 0.95 and closes[-1] > channel_high:
            k[i] = 1
        elif cons_low < channel_low * 1.05 and closes[-1] < channel_low:
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
    return run_backtest(df, calc_chan_donchian_double, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
