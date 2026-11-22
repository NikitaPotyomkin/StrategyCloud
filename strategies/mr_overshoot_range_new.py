"""Strategy: mr_overshoot_range (H1).

Idea: > 130% ADR passed — возврат 30% движения.
Вход: пройдено > 130% ADR → fade 30% движения.
Выход: 30% откат.
Отличие: ADR exhaustion mean reversion.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_mr_overshoot_range(df, period=20):
    """Mean reversion on ADR overshoot.
    
    > 130% ADR passed → fade 30% of move.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        opens = df['open'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Daily range
        daily_range = np.max(highs) - np.min(lows)
        
        # ADR (average daily range)
        adr = df['high'].rolling(20).max() - df['low'].rolling(20).min()
        adr_mean = adr.rolling(20).mean().iloc[i]
        
        # Overshoot > 130% ADR
        if adr_mean > 0 and daily_range > 1.3 * adr_mean:
            # Fade
            if closes[-1] > opens[-1]:
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
    return run_backtest(df, calc_mr_overshoot_range, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
