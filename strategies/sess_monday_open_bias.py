"""Strategy: sess_monday_open_bias (H1).

Idea: Monday opens in Friday close direction — Monday bias.
Вход: Monday open > Friday close + тренд → сигнал.
Выход: конец Monday.
Отличие: Monday open часто продолжает Friday close.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_sess_monday_open_bias(df, period=20):
    """Monday open bias strategy.
    
    Monday opens in Friday close direction.
    Trade with bias on Monday.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        opens = df['open'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Monday open bias
        if opens[-1] > closes[-2]:  # Gap up
            # Check trend
            sma50 = df['close'].rolling(50).mean().iloc[i]
            if closes[-1] > sma50:
                k[i] = 1
        elif opens[-1] < closes[-2]:  # Gap down
            sma50 = df['close'].rolling(50).mean().iloc[i]
            if closes[-1] < sma50:
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
    return run_backtest(df, calc_sess_monday_open_bias, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
