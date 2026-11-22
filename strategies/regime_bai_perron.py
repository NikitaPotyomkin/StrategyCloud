"""Strategy: regime_bai_perron (H1).

Idea: 2+ change-points in 300 bars — Bai-Perron test.
Вход: multiple change-points → signal.
Выход: 1 день.
Отличие: multiple structural breaks.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_regime_bai_perron(df, period=20):
    """Bai-Perron multiple change-points.
    
    Multiple change-points detected → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Simple multiple change-point detection
        n = len(closes)
        chunk_size = n // 3
        
        means = [np.mean(closes[:chunk_size]), np.mean(closes[chunk_size:2*chunk_size]), np.mean(closes[2*chunk_size:])]
        
        # Count significant changes
        changes = 0
        for j in range(len(means) - 1):
            if abs(means[j+1] - means[j]) > 0.5 * np.std(closes):
                changes += 1
        
        # Multiple changes
        if changes >= 2:
            if means[-1] > means[0]:
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
    return run_backtest(df, calc_regime_bai_perron, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
