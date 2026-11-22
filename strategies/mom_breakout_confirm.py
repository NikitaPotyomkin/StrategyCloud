"""Momentum: Breakout Confirmation (H1).

Idea: 0312 mom_breakout_confirm
Вход: momentum(20) > 0 AND breakout high(20)
Выход: momentum < 0
Отличие: Dual confirmation - momentum + price action
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest


def calc_mom_breakout_confirm(df, period=20):
    mom = df['close'] - df['close'].shift(period)
    high_20 = df['high'].rolling(period).max()
    low_20 = df['low'].rolling(period).min()

    k = np.zeros(len(df))
    k[(mom > 0) & (df['close'] > high_20.shift(1))] = 1
    k[(mom < 0) & (df['close'] < low_20.shift(1))] = -1

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
    return run_backtest(df, calc_mom_breakout_confirm, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
