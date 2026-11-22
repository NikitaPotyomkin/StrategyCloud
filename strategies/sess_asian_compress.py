"""Session: Asian Compression (H1).

Idea: 0364 sess_asian_compress
Вход: азиатский диапазон < p25(60 дней) -> пробой в Лондоне;
      выход: 2× диапазона.
Отличие: сжатие Азии часто предшествует движению в Лондоне.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 4-12 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_sess_asian_compress(df, period=60):
    # Range бара как прокси сессионного диапазона
    bar_range = df['high'] - df['low']

    # p25 диапазона за period
    range_p25 = bar_range.rolling(period).quantile(0.25)

    # Сжатие: range < p25
    is_compress = bar_range < range_p25

    # Пробой после сжатия
    high_compress = df['high'].rolling(2).max().shift(1)
    low_compress = df['low'].rolling(2).min().shift(1)

    k = np.zeros(len(df))
    k[is_compress & (df['close'] > high_compress)] = 1
    k[is_compress & (df['close'] < low_compress)] = -1

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
    return run_backtest(df, calc_sess_asian_compress, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
