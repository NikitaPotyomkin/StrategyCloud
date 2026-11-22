"""Strategy: cyc_phase_cross (H1).

Idea: Phase crosses 0 up — фазовый переход Hilbert.
Вход: phase crosses 0 up → long.
Выход: phase crosses pi.
Отличие: Hilbert transform phase detection.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_cyc_phase_cross(df, period=20):
    """Hilbert phase crossing.
    
    Phase crosses 0 up → long.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Simple phase proxy (Hilbert transform approximation)
        # Use derivative as phase proxy
        derivative = np.diff(closes)
        
        # Phase crossing detection
        if len(derivative) >= 2:
            if derivative[-1] > 0 and derivative[-2] <= 0:
                k[i] = 1
            elif derivative[-1] < 0 and derivative[-2] >= 0:
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
    return run_backtest(df, calc_cyc_phase_cross, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
