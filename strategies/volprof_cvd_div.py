"""Volume Profile: CVD Divergence (H1).

Idea: 0087 volprof_cvd_div
Вход: CVD растёт, цена падает (дивергенция);
      выход: CVD разворот.
Отличие: CVD (Cumulative Volume Delta) показывает давление покупателей/продавцов.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 8-24 бара.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_volprof_cvd_div(df, period=50):
    ret = df['close'].pct_change().fillna(0)

    # CVD proxy: накопленный объём с направлением
    # Positive volume: close > open
    # Negative volume: close < open
    vol_direction = np.where(df['close'] > df['open'], df['volume'], -df['volume'])
    cvd = pd.Series(vol_direction).cumsum()

    # Дивергенция: CVD растёт, цена падает
    cvd_trend = cvd.diff(10) > 0  # CVD растёт за 10 баров
    price_fall = df['close'] < df['close'].shift(10)

    # Обратная дивергенция: CVD падает, цена растёт
    cvd_fall = cvd.diff(10) < 0
    price_rise = df['close'] > df['close'].shift(10)

    k = np.zeros(len(df))
    k[cvd_trend & price_fall] = 1   # Long: CVD растёт, цена упала
    k[cvd_fall & price_rise] = -1   # Short: CVD падает, цена выросла

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
    return run_backtest(df, calc_volprof_cvd_div, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
