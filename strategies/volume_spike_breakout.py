"""Volume Spike Breakout (каталог #88).

Сигнал: объём > K× среднего за N баров + пробой N-барного экстремума.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 / -1 при спайке и пробое, иначе 0.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

VOL_MULT = 2.0


def calc_volume_spike(df, period):
    """period — окно среднего объёма и канала пробоя. Колонка 'k' — состояние."""
    avg_vol = df['volume'].rolling(period, min_periods=period).mean()
    spike = df['volume'] > VOL_MULT * avg_vol
    up = df['high'].rolling(period, min_periods=period).max().shift(1)
    dn = df['low'].rolling(period, min_periods=period).min().shift(1)
    state = np.where(spike & (df['close'] > up), 1,
                     np.where(spike & (df['close'] < dn), -1, 0))
    df = df.copy()
    df['k'] = state
    return df


def check_entry(prev_s, curr_s):
    return state_entry(prev_s, curr_s)


def check_exit(prev_s, curr_s, direction):
    return state_exit(prev_s, curr_s, direction)


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_volume_spike, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
