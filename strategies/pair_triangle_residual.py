"""Strategy: pair_triangle_residual (H1).

Idea: Triangle nonlinearity > 2sigma — треугольная арбитратаж.
Вход: residual > 2σ → signal.
Выход: 0.
Отличие: triangle arbitrage между 3 активами.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pair_triangle_residual(df, period=20):
    """Triangle residual detection.
    
    Triangle nonlinearity > 2σ → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Simple triangle residual proxy
        # A/B * B/C - A/C > 2sigma
        ret1 = np.diff(closes[:len(closes)//2])
        ret2 = np.diff(closes[len(closes)//2:])
        
        if len(ret1) > 0 and len(ret2) > 0:
            residual = np.mean(ret1) - np.mean(ret2)
            std_res = np.std(np.concatenate([ret1, ret2]))
            
            if std_res > 0 and abs(residual) > 2 * std_res:
                if residual > 0:
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
    return run_backtest(df, calc_pair_triangle_residual, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
