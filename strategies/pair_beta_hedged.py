"""Strategy: pair_beta_hedged (H1).

Idea: Beta-hedged pair residual z > 2 — бета-хеджирование.
Вход: residual z > 2 → signal.
Выход: z < 0.
Отличие: beta-hedged pair消除 market risk.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pair_beta_hedged(df, period=20):
    """Beta-hedged pair residual.
    
    Residual z > 2 → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Beta-hedge proxy
        market_ret = np.mean(np.diff(closes))
        asset_ret = closes[-1] - closes[-2]
        
        # Residual
        beta = 1.0  # Simplified
        residual = asset_ret - beta * market_ret
        
        # Z-score
        if i > 10:
            prev_res = []
            for j in range(max(0, i-10), i):
                mr = np.mean(np.diff(df['close'].iloc[j-10:j]))
                ar = df['close'].iloc[j] - df['close'].iloc[j-1]
                prev_res.append(ar - beta * mr)
            
            z = residual / np.std(prev_res) if np.std(prev_res) > 0 else 0
            
            if abs(z) > 2.0:
                if z > 0:
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
    return run_backtest(df, calc_pair_beta_hedged, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
