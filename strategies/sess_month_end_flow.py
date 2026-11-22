"""Strategy: sess_month_end_flow (H1).

Idea: Last 2 days of month: rebalancing — конец месяца.
Вход: последние 2 дня месяца → разворот к rebalancing.
Выход: 2 дня удержания.
Отличие: month end rebalancing — календарный эффект.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_sess_month_end_flow(df, period=20):
    """Month end rebalancing strategy.
    
    Last 2 days of month: rebalancing flow.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Mean reversion at month end
        if closes[-1] > closes[-2]:
            k[i] = -1
        elif closes[-1] < closes[-2]:
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
    return run_backtest(df, calc_sess_month_end_flow, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
