"""Momentum: Acceleration Z-Score (H1).

Idea: 0283 mom_accel_z
Вход: acceleration z > 2
Выход: z < 0
Отличие: Third derivative (jerk) proxy
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest


def calc_mom_accel_z(df, period=20):
    price_accel = df['close'].diff(2) - df['close'].diff(2).shift(1)
    rolling_mean = price_accel.rolling(period).mean()
    rolling_std = price_accel.rolling(period).std()
    z = (price_accel - rolling_mean) / rolling_std.replace(0, np.nan)

    k = np.zeros(len(df))
    k[z > 2.0] = 1
    k[z < -2.0] = -1

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
    """Симуляция сделок через общий движок strategies/_bt_core.run_backtest.

    Прежняя собственная петля входила по close сигнального бара (цена закрытия
    уже известна в момент входа), не вычитала спред, выбрасывала сделки, не
    закрывшиеся за 49 баров, и считала P&L как diff * lot * tick_value без
    деления на tick_size — из-за этого её числа были несравнимы с остальным
    реестром. Замер: tools/loop_model_pilot.py.
    """
    return run_backtest(df, calc_mom_accel_z, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
