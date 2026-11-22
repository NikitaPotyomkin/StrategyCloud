"""Strategy: stat_cross_corr_lag (H1).

Idea: Max cross-correlation at lag > 0 — лаговая корреляция.
Вход: max cross-corr at lag > 0 → signal.
Выход: когда lag changes sign.
Отличие: cross-correlation с лагом.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_cross_corr_lag(df, period=20):
    """Cross-correlation at lag detection.
    
    Max cross-correlation at lag > 0.
    Signal when lag confirmed.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        returns = np.diff(closes)
        
        if len(returns) > 10:
            # Cross-correlation at lag 1-3
            max_corr = 0
            max_lag = 0
            
            for lag in range(1, 4):
                if len(returns) > lag:
                    corr = np.corrcoef(returns[:-lag], returns[lag:])[0, 1]
                    if abs(corr) > abs(max_corr):
                        max_corr = corr
                        max_lag = lag
            
            # Signal if significant lagged correlation
            if abs(max_corr) > 0.3 and max_lag > 0:
                if max_corr > 0:
                    k[i] = 1 if returns[-1] > 0 else -1
                else:
                    k[i] = -1 if returns[-1] > 0 else 1
    
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
    return run_backtest(df, calc_stat_cross_corr_lag, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
