"""Anomaly Detection: Huge Volume Spike (H1).

Idea: 0934 anom_huge_volume
Вход: объём > 10×медиана(100);
      выход через 5 баров (пауза после аномального объёма).
Отличие: huge volume spike = аномальный интерес институционалов.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 5-15 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_anom_huge_volume(df, period=100):
    vol_median = df['volume'].rolling(period).median()

    # Volume spike > 10× медиана
    vol_spike = df['volume'] > 10 * vol_median.replace(0, np.nan).fillna(1)

    # Направление по close
    k = np.zeros(len(df))
    k[vol_spike & (df['close'] > df['open'])] = 1
    k[vol_spike & (df['close'] < df['open'])] = -1

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
    return run_backtest(df, calc_anom_huge_volume, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
