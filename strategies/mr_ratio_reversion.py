"""Strategy: mr_ratio_reversion (H1).

Idea: Currency strength index deviation > 2sigma — возврат к 0.
Вход: отклонение strength > 2σ → fade.
Выход: 0.
Отличие: currency strength mean reversion.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_mr_ratio_reversion(df, period=20):
    """Currency strength mean reversion.
    
    Strength deviation > 2σ → fade to 0.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Returns as proxy for strength
        returns = np.diff(closes)
        
        # Strength (cumulative returns)
        strength = np.cumsum(returns)
        
        # Z-score
        z = strength[-1] / np.std(strength) if np.std(strength) > 0 else 0
        
        # Fade when z > 2
        if abs(z) > 2.0:
            if z > 0:
                k[i] = -1
            else:
                k[i] = 1
    
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
    return run_backtest(df, calc_mr_ratio_reversion, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
