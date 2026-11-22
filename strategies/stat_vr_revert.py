"""Strategy: stat_vr_revert (H1).

Idea: Variance ratio VR(5) < 0.8 (reversion) — возврат к среднему.
Вход: VR < 0.8 → mean reversion сигнал.
Выход: VR > 1.0.
Отличие: variance ratio тест на reversion vs random walk.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_vr_revert(df, period=20):
    """Variance ratio test for mean reversion.
    
    VR(5) < 0.8 indicates mean reversion.
    Signal in opposite direction of recent return.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Calculate returns
        returns = np.diff(closes)
        
        if len(returns) < 5:
            continue
        
        # Variance ratio VR(5)
        var_1 = np.var(returns[-1:])
        var_5 = np.var(returns[-5:]) / 5
        
        if var_1 > 0:
            vr = var_5 / var_1
            
            # VR < 0.8 → mean reversion
            if vr < 0.8:
                # Fade recent return
                if returns[-1] > 0:
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
    return run_backtest(df, calc_stat_vr_revert, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
