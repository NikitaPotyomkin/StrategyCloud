"""HH/LL sequence, каталог #112.

Сигнал: серия из N подряд higher-high → LONG; серия lower-low → SHORT.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_hh_ll(df, period):
    """period — длина серии. Колонка 'k' — состояние позиции."""
    hh = (df['high'].diff() > 0).astype(int)
    ll = (df['low'].diff() < 0).astype(int)
    hh_run = hh.rolling(period, min_periods=period).sum()
    ll_run = ll.rolling(period, min_periods=period).sum()
    up = hh_run >= period
    dn = ll_run >= period
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
    return run_backtest(df, calc_hh_ll, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
