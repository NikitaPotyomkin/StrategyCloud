"""Strategy: advstat_fractal_dim_new (H1).

Idea: Fractal dimension < 1.5 — фрактальная размерность.
Вход: FD < 1.5 → trend.
Выход: FD > 1.7.
Отличие: fractal dimension regime detection.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_advstat_fractal_dim_new(df, period=20):
    """Fractal dimension detection.
    
    FD < 1.5 → trend signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Fractal dimension proxy (R/S analysis)
        returns = np.diff(closes)
        
        # Mean and std
        mean_ret = np.mean(returns)
        std_ret = np.std(returns)
        
        if std_ret > 0:
            # R/S
            cum_ret = np.cumsum(returns - mean_ret)
            range_ret = np.max(cum_ret) - np.min(cum_ret)
            rs = range_ret / std_ret
            
            # Fractal dimension proxy
            fd = 2 - np.log(rs) / np.log(len(returns))
            
            # Signal
            if fd < 1.5:
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
    return run_backtest(df, calc_advstat_fractal_dim_new, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
