"""Momentum breakout, каталог #75.

Сигнал: моментум (close − close[period]) выходит за порог в ±k·σ моментума.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

SIGMA_MULT = 2.0


def calc_momentum_threshold(df, period):
    """period — окно моментума. Колонка 'k' — состояние позиции."""
    mom = df['close'] - df['close'].shift(period)
    sigma = mom.rolling(period, min_periods=period).std(ddof=0).replace(0.0, np.nan)
    thresh = SIGMA_MULT * sigma
    up = mom > thresh
    dn = mom < -thresh
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
    return run_backtest(df, calc_momentum_threshold, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
