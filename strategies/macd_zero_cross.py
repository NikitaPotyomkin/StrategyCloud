"""MACD zero-line cross (каталог #50).

Сигнал: линия MACD пересекает ноль (смена среднесрочного тренда).
Standalone-модуль: не подключён к main/dispatcher.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest

FAST = 12
SLOW = 26


def calc_macd_zero(df, period):
    """MACD = EMA(fast) - EMA(slow); period игнорируется (константы MACD). Колонка 'k'."""
    ema_fast = df['close'].ewm(span=FAST, adjust=False).mean()
    ema_slow = df['close'].ewm(span=SLOW, adjust=False).mean()
    macd = ema_fast - ema_slow
    df = df.copy()
    df['k'] = macd.fillna(0.0)
    return df


def check_entry(prev_k, curr_k):
    if prev_k <= 0.0 and curr_k > 0.0:
        return 'long'
    if prev_k >= 0.0 and curr_k < 0.0:
        return 'short'
    return None


def check_exit(prev_k, curr_k, direction):
    if direction == 'long':
        return prev_k >= 0.0 and curr_k < 0.0
    return prev_k <= 0.0 and curr_k > 0.0


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_macd_zero, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
