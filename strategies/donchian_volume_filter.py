"""Donchian + Volume filter, каталог #63.

Сигнал: пробой N-барного максимума/минимума при объёме выше среднего.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

VOL_PERIOD = 20
VOL_MULT = 1.0


def calc_donchian_volume(df, period):
    """period — окно Donchian. Колонка 'k' — состояние позиции."""
    hi = df['high'].rolling(period, min_periods=period).max().shift(1)
    lo = df['low'].rolling(period, min_periods=period).min().shift(1)
    vol_avg = df['volume'].rolling(VOL_PERIOD, min_periods=VOL_PERIOD).mean()
    vol_ok = df['volume'] > VOL_MULT * vol_avg
    up = (df['close'] > hi) & vol_ok
    dn = (df['close'] < lo) & vol_ok
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
    return run_backtest(df, calc_donchian_volume, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
