"""Strategy: regime_pelt_proxy (H1).

Idea: PELT-proxy (penalized SSE) finds change-point — точка изменения.
Вход: change-point detected → signal.
Выход: 1 день.
Отличие: PELT change-point detection.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_regime_pelt_proxy(df, period=20):
    """PELT change-point detection proxy.
    
    Change-point detected → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Simple change-point detection
        mid = len(closes) // 2
        
        mean1 = np.mean(closes[:mid])
        mean2 = np.mean(closes[mid:])
        
        # SSE before and after
        sse_before = np.sum((closes[:mid] - mean1)**2)
        sse_after = np.sum((closes[mid:] - mean2)**2)
        sse_total = np.sum((closes - np.mean(closes))**2)
        
        # Reduction in SSE
        reduction = (sse_total - sse_before - sse_after) / sse_total
        
        # Change-point detected
        if reduction > 0.1:
            if mean2 > mean1:
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
    return run_backtest(df, calc_regime_pelt_proxy, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
