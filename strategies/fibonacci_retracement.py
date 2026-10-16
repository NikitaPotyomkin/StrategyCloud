"""Fibonacci Retracement, каталог #109.

Сигнал: коррекция к уровню 38.2–61.8% свинга в направлении тренда SMA.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

FIB_LOW = 0.382
FIB_HIGH = 0.618


def calc_fibonacci(df, period):
    """period — окно свинга. Колонка 'k' — состояние позиции."""
    swing_hi = df['high'].rolling(period, min_periods=period).max().shift(1)
    swing_lo = df['low'].rolling(period, min_periods=period).min().shift(1)
    rng = (swing_hi - swing_lo).replace(0.0, np.nan)
    retr = (swing_hi - df['close']) / rng
    trend = df['close'].ewm(span=2 * period, adjust=False).mean()
    up = (df['close'] > trend) & (retr >= FIB_LOW) & (retr <= FIB_HIGH)
    dn = (df['close'] < trend) & (retr >= FIB_LOW) & (retr <= FIB_HIGH)
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
    return run_backtest(df, calc_fibonacci, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
