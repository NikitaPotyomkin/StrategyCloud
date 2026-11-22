"""Strategy: stat_jarque_bera (H1).

Idea: JB p < 0.01 (heavy tails) — тяжелые хвосты.
Вход: JB significant → reduce risk / signal.
Выход: когда JB not significant.
Отличие: Jarque-Bera тест на нормальность (heavy tails).

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_jarque_bera(df, period=20):
    """Jarque-Bera test for normality.
    
    JB p < 0.01 indicates heavy tails.
    Signal on heavy tails.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        returns = np.diff(closes)
        
        if len(returns) > 10:
            # Skewness and kurtosis
            mean_ret = np.mean(returns)
            std_ret = np.std(returns)
            
            if std_ret > 0:
                skew = np.sum(((returns - mean_ret) / std_ret)**3) / len(returns)
                kurt = np.sum(((returns - mean_ret) / std_ret)**4) / len(returns)
                
                # JB statistic
                jb = len(returns) / 6 * (skew**2 + (kurt - 3)**2 / 4)
                
                # JB > 5.99 (p < 0.05)
                if jb > 5.99:
                    # Signal on heavy tails
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
    return run_backtest(df, calc_stat_jarque_bera, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
