"""Session: Hour of Day Bias (H1).

Idea: 0372 sess_hour_of_day
Вход: час с положительным средним ret(60 дней);
      выход: конец часа.
Отличие: некоторые часы статистически выгоднее других.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 1-4 бара.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_sess_hour_of_day(df, period=60):
    ret = df['close'].pct_change().fillna(0)

    # Средний ret по "часу" (прокси: позиция в rolling window)
    # Используем rolling mean ret как прокси hourly bias
    hourly_bias = ret.rolling(period).mean()

    # Положительный bias -> long, отрицательный -> short
    k = np.zeros(len(df))
    k[hourly_bias > 0.0001] = 1   # Положительный bias
    k[hourly_bias < -0.0001] = -1  # Отрицательный bias

    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Returns 'long' / 'short' / None for engine run_backtest
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
    return run_backtest(df, calc_sess_hour_of_day, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
