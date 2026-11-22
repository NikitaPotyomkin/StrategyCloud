"""Strategy: volprof_vol_imbalance (H1).

Idea: Up-bar volume / down-bar volume > 1.5 — дисбаланс объёма.
Вход: volume imbalance > 1.5 → signal.
Выход: < 1.0.
Отличие: volume imbalance между up/down барами.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_volprof_vol_imbalance(df, period=20):
    """Volume imbalance detection.
    
    Up-bar volume / down-bar volume > 1.5 → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        volumes = df['volume'].iloc[i-period:i].values
        
        # Separate up and down bar volumes
        up_vol = np.sum(volumes[closes > np.roll(closes, 1)])
        down_vol = np.sum(volumes[closes <= np.roll(closes, 1)])
        
        # Volume imbalance
        if down_vol > 0:
            imbalance = up_vol / down_vol
            
            if imbalance > 1.5:
                k[i] = 1
            elif imbalance < 0.67:
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
    return run_backtest(df, calc_volprof_vol_imbalance, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
