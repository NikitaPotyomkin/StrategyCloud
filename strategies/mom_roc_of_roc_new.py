"""Strategy: mom_roc_of_roc (H1).

Idea: ROC of ROC — ускорение momentum.
Вход: ROC accelerating → signal.
Выход: ROC decelerating.
Отличие: second derivative of price.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_mom_roc_of_roc(df, period=20):
    """ROC of ROC (acceleration).
    
    ROC accelerating → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # ROC
        roc = np.diff(closes)
        
        # ROC of ROC
        roc_of_roc = np.diff(roc)
        
        # Signal
        if len(roc_of_roc) > 0:
            if roc_of_roc[-1] > 0:
                k[i] = 1
            elif roc_of_roc[-1] < 0:
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
    return run_backtest(df, calc_mom_roc_of_roc, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
