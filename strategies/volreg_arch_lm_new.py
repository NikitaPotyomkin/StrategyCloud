"""Strategy: volreg_arch_lm (H1).

Idea: ARCH-LM p-value(60) < 0.05 — ARCH эффект.
Вход: ARCH significant → signal.
Выход: 10 баров.
Отличие: ARCH-LM test vol clustering.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_volreg_arch_lm(df, period=20):
    """ARCH-LM test for volatility clustering.
    
    ARCH significant → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        returns = np.diff(closes)**2
        
        # ARCH LM proxy
        if len(returns) > 10:
            # Regress returns^2 on lag
            lag_returns = returns[:-1]**2
            current_returns = returns[1:]**2
            
            # Correlation
            corr = np.corrcoef(lag_returns, current_returns)[0, 1]
            
            # ARCH significant
            if abs(corr) > 0.3:
                if returns[-1] > np.mean(returns):
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
    return run_backtest(df, calc_volreg_arch_lm, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
