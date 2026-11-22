"""Strategy: stat_kl_divergence (H1).

Idea: KL(p_now || p_30_bars) > threshold — расхождение распределений.
Вход: KL divergence > threshold → signal.
Выход: когда < threshold.
Отличие: KL divergence на распределении returns.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_kl_divergence(df, period=20):
    """KL divergence detection.
    
    KL(p_now || p_30_bars) > threshold.
    Signal on distribution shift.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        returns = np.diff(closes)
        
        if len(returns) > 10:
            # Split into two halves
            half = len(returns) // 2
            returns1 = returns[:half]
            returns2 = returns[half:]
            
            # Histograms
            bins = np.histogram(returns1, bins=10)[0] + 1  # +1 to avoid 0
            probs1 = bins / np.sum(bins)
            
            bins = np.histogram(returns2, bins=10)[0] + 1
            probs2 = bins / np.sum(bins)
            
            # KL divergence
            kl_div = np.sum(probs1 * np.log(probs1 / probs2))
            
            # Signal on significant divergence
            if kl_div > 0.5:
                if returns2[-1] > 0:
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
    return run_backtest(df, calc_stat_kl_divergence, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
