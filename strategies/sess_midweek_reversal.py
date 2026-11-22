"""Strategy: sess_midweek_reversal (H1).

Idea: Midweek reversal после 2-дневного тренда — разворот в среду.
Вход: 2+ дней тренда + среда → разворот.
Выход: 1 день удержания.
Отличие: midweek reversal — календарный аномалия.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_sess_midweek_reversal(df, period=20):
    """Midweek reversal after 2-day trend.
    
    Detects 2+ day trend then reversal on midweek.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Check for 2+ day trend
        if closes[-1] > closes[-2] > closes[-3]:  # Uptrend
            k[i] = -1  # Reversal short
        elif closes[-1] < closes[-2] < closes[-3]:  # Downtrend
            k[i] = 1  # Reversal long
    
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
    return run_backtest(df, calc_sess_midweek_reversal, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
