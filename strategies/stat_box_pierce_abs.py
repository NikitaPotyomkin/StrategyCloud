"""Strategy: stat_box_pierce_abs (H1).

Idea: LB on |ret| (volatility clustering) — кластер волатильности.
Вход: LB test на |ret| significant → signal.
Выход: 4 бара удержания.
Отличие: volatility clustering — кластер волатильности.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_box_pierce_abs(df, period=20):
    """Box-Pierce test on absolute returns.
    
    Detects volatility clustering.
    Signal in direction of clustering.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Calculate absolute returns
        returns = np.abs(np.diff(closes))
        
        if len(returns) < 5:
            continue
        
        # Box-Pierce test proxy
        var_ret = np.var(returns)
        if var_ret > 0:
            mean_ret = np.mean(returns)
            sq_diff = (returns - mean_ret)**2
            bp_stat = np.sum(sq_diff) / (var_ret * len(returns))
            
            # If significant clustering
            if bp_stat > 1.0:
                # Signal in direction of recent return
                if closes[-1] > closes[-2]:
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
    return run_backtest(df, calc_stat_box_pierce_abs, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
