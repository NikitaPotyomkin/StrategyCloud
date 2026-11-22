"""Strategy: pair_vol_adjusted (H1).

Idea: Z by sigma-normalized spread > 2 — волатильность-скорректированная пара.
Вход: vol-adjusted z > 2 → signal.
Выход: 0.
Отличие: vol-adjusted spread消除 vol regime bias.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pair_vol_adjusted(df, period=20):
    """Volatility-adjusted pair spread.
    
    Vol-adjusted z > 2 → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Vol-adjusted returns
        returns = np.diff(closes)
        
        # Rolling volatility
        vol = np.std(returns)
        
        if vol > 0:
            # Normalized spread
            spread = np.cumsum(returns / vol)
            
            # Z-score
            if len(spread) > 5:
                z = spread[-1] / np.std(spread)
                
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
    return run_backtest(df, calc_pair_vol_adjusted, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
