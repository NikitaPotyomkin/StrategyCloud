"""Strategy: mr_weekly_deviation (H1).

Idea: Deviation from weekly mean > 2sigma — возврат к weekly mean.
Вход: цена далеко от weekly mean → fade.
Выход: weekly mean.
Отличие: weekly mean reversion.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_mr_weekly_deviation(df, period=20):
    """Mean reversion to weekly mean.
    
    Deviation from weekly mean > 2σ → fade signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Weekly mean (rolling)
        weekly_mean = np.mean(closes)
        weekly_std = np.std(closes)
        
        # Deviation > 2σ
        if weekly_std > 0:
            deviation = abs(closes[-1] - weekly_mean) / weekly_std
            
            if deviation > 2.0:
                if closes[-1] > weekly_mean:
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
    return run_backtest(df, calc_mr_weekly_deviation, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
