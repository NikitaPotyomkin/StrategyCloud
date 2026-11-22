"""Anomaly Detection: Stop Run / Liquidity Sweep (H1).

Idea: 0923 anom_stop_run
Вход: прокол экстремума 20 баров + возврат за 2 бара;
      вход в сторону возврата (fade прокола).
Выход: противоположный экстремум или trail 1.5×ATR.
Отличие: stop run = цена пробивает уровень, но быстро возвращается.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 4-8 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_anom_stop_run(df, period=20):
    high_20 = df['high'].rolling(period).max()
    low_20 = df['low'].rolling(period).min()

    # Пробой экстремума
    broke_high = df['high'] > high_20.shift(1)
    broke_low = df['low'] < low_20.shift(1)

    # Возврат внутрь диапазона за 2 бара
    closed_back_high = df['close'] < high_20.shift(1)
    closed_back_low = df['close'] > low_20.shift(1)

    # Stop run: прокол + возврат
    is_stop_high = broke_high & closed_back_high
    is_stop_low = broke_low & closed_back_low

    # Fade: short на проколе high, long на проколе low
    k = np.zeros(len(df))
    k[is_stop_high] = -1
    k[is_stop_low] = 1

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
    return run_backtest(df, calc_anom_stop_run, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
