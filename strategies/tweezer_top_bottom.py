"""Tweezer Top/Bottom, каталог #84.

Сигнал: две свечи с близкими экстремумами — Bottom (два минимума) → LONG,
Top (два максимума) → SHORT.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, atr, state_entry, state_exit

ATR_PERIOD = 14
TOL_MULT = 0.15


def calc_tweezer(df, period):
    """period — период ATR для допуска. Колонка 'k' — состояние позиции."""
    atr_v = atr(df, ATR_PERIOD)
    tol = TOL_MULT * atr_v
    low, high = df['low'], df['high']
    bottom = (low - low.shift(1)).abs() <= tol
    top = (high - high.shift(1)).abs() <= tol
    up = bottom & (df['close'] > df['open'])
    dn = top & (df['close'] < df['open'])
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
    return run_backtest(df, calc_tweezer, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
