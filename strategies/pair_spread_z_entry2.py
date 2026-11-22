"""Strategy: pair_spread_z_entry2 (H1).

Idea: Spread z > 2 (short spread) — mean reversion spread.
Вход: z > 2 → short spread.
Выход: z < 0.
Отличие: pair spread mean reversion на z-score.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pair_spread_z_entry2(df, period=20):
    """Pair spread z-score mean reversion.
    
    Spread z > 2 → short spread.
    Exit when z < 0.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Spread as returns
        returns = np.diff(closes)
        spread = np.cumsum(returns)
        
        # Z-score
        if len(spread) > 5:
            z = (spread[-1] - np.mean(spread)) / np.std(spread)
            
            if z > 2.0:
                k[i] = -1
            elif z < -2.0:
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
    return run_backtest(df, calc_pair_spread_z_entry2, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
