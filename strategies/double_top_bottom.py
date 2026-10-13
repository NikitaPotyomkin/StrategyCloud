"""Double Top/Bottom, каталог #111.

Сигнал: повторное касание экстремума (двойная вершина/дно) с разворотом.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, atr, state_entry, state_exit

TOL_MULT = 0.25


def calc_double_top_bottom(df, period):
    """period — окно поиска экстремумов. Колонка 'k' — состояние позиции."""
    swing_hi = df['high'].rolling(period, min_periods=period).max()
    swing_lo = df['low'].rolling(period, min_periods=period).min()
    atr_v = atr(df, 14)
    tol = TOL_MULT * atr_v
    near_hi = (swing_hi - df['high']).abs() <= tol
    near_lo = (df['low'] - swing_lo).abs() <= tol
    up = near_lo & (df['close'] > df['open'])
    dn = near_hi & (df['close'] < df['open'])
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
    return run_backtest(df, calc_double_top_bottom, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
