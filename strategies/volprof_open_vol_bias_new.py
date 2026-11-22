"""Strategy: volprof_open_vol_bias (H1).

Idea: Объём первых 3 баров дня задаёт направление дня — open volume bias.
Вход: open volume bias → signal.
Выход: конец дня.
Отличие: open volume directional bias.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_volprof_open_vol_bias(df, period=20):
    """Open volume bias detection.
    
    First 3 bars volume sets day direction.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        volumes = df['volume'].iloc[i-period:i].values
        
        # First 3 bars volume
        open_vol = np.sum(volumes[:3])
        total_vol = np.sum(volumes)
        
        # Open volume ratio
        open_ratio = open_vol / total_vol if total_vol > 0 else 0
        
        # Direction
        if open_ratio > 0.3:
            if closes[2] > closes[0]:
                k[i] = 1
            elif closes[2] < closes[0]:
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
    return run_backtest(df, calc_volprof_open_vol_bias, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
