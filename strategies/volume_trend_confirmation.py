"""Volume trend confirmation, каталог #94.

Сигнал: цена выше/ниже значения N баров назад И объём выше среднего → вход по тренду.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

VOL_MULT = 1.0


def calc_volume_trend(df, period):
    """period — окно тренда. Колонка 'k' — состояние позиции."""
    ref = df['close'].shift(period)
    vol_avg = df['volume'].rolling(period, min_periods=period).mean()
    vol_ok = df['volume'] > VOL_MULT * vol_avg
    up = (df['close'] > ref) & vol_ok
    dn = (df['close'] < ref) & vol_ok
    df = df.copy()
    df['k'] = np.where(up, 1, np.where(dn, -1, 0))
    return df


def check_entry(prev_s, curr_s):
    return state_entry(prev_s, curr_s)


def check_exit(prev_s, curr_s, direction):
    return state_exit(prev_s, curr_s, direction)


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_volume_trend, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
