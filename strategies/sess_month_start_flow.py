"""Strategy: sess_month_start_flow (H1).

Idea: First 2 days of month: buying flow — начало месяца.
Вход: первые 2 дня месяца в направлении тренда → сигнал.
Выход: 3 дня удержания.
Отличие: month start flow — календарный эффект.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_sess_month_start_flow(df, period=20):
    """Month start flow strategy.
    
    First 2 days of month: buying/selling flow.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # First 2 days of month flow
        if closes[-1] > closes[-2] and closes[-2] > closes[-3]:
            k[i] = 1
        elif closes[-1] < closes[-2] and closes[-2] < closes[-3]:
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
    return run_backtest(df, calc_sess_month_start_flow, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
