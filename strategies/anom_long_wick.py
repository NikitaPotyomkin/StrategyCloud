"""Anomaly Detection: Long Wick at Extreme (H1).

Idea: 0933 anom_long_wick
Вход: тень > 70% диапазона на экстремуме 50 баров;
      выход: 1.5×ATR (fade длинной тени).
Отличие: long wick = длинная тень свечи на экстремуме указывает на отказ от уровня.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 4-8 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_anom_long_wick(df, period=50):
    high_period = df['high'].rolling(period).max()
    low_period = df['low'].rolling(period).min()

    # Длина тени
    upper_wick = df['high'] - df[['close', 'open']].max(axis=1)
    lower_wick = df[['close', 'open']].min(axis=1) - df['low']
    body = (df['close'] - df['open']).abs()
    total_range = df['high'] - df['low']

    # Тень > 70% диапазона
    long_upper = upper_wick > 0.7 * total_range
    long_lower = lower_wick > 0.7 * total_range

    # На экстремуме
    at_high_extreme = df['high'] >= high_period
    at_low_extreme = df['low'] <= low_period

    # Long upper wick at high extreme -> fade (short)
    k = np.zeros(len(df))
    k[long_upper & at_high_extreme] = -1

    # Long lower wick at low extreme -> fade (long)
    k[long_lower & at_low_extreme] = 1

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
    return run_backtest(df, calc_anom_long_wick, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
