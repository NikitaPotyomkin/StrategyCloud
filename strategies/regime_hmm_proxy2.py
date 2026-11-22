"""Strategy: regime_hmm_proxy2 (H1).

Idea: 2-state Markov (ret + sigma): transition to "trend" — марковский процесс.
Вход: transition to "trend" → signal.
Выход: transition to "flat".
Отличие: HMM proxy для regime detection.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_regime_hmm_proxy2(df, period=20):
    """2-state Markov proxy.
    
    Transition to "trend" → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        returns = np.diff(closes)
        
        # State 1: trend (high |ret|)
        # State 2: flat (low |ret|)
        threshold = np.std(returns)
        
        # Current state
        if abs(returns[-1]) > threshold:
            # Trend state
            if returns[-1] > 0:
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
    return run_backtest(df, calc_regime_hmm_proxy2, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
