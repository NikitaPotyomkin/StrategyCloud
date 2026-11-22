"""Strategy: stat_sign_test (H1).

Idea: Sign test drift: 60%+ positives from 40 — тест знаков.
Вход: 60%+ positive returns → long; < 40% → short.
Выход: когда < 50%.
Отличие: non-parametric sign test на drift.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_sign_test(df, period=20):
    """Sign test for drift detection.
    
    60%+ positive returns → long; < 40% → short.
    Exit when < 50%.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        returns = np.diff(closes)
        
        if len(returns) >= 10:
            # Count positive returns
            n_pos = np.sum(returns > 0)
            n_total = len(returns)
            
            pct_pos = n_pos / n_total
            
            # Signal on significant drift
            if pct_pos > 0.60:
                k[i] = 1
            elif pct_pos < 0.40:
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
    return run_backtest(df, calc_stat_sign_test, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
