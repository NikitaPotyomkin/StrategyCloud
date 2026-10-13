"""MACD line crossover, каталог #47.

Сигнал: линия MACD пересекает сигнальную линию (вверх → LONG, вниз → SHORT).
Standalone-модуль: не подключён к main/dispatcher.
Колонка 'k' — разность (MACD − сигнал), value-cross нуля.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest

SIGNAL_PERIOD = 9


def calc_macd_line(df, period):
    """period — быстрый период (медленный = 2·period + 2). Колонка 'k' = MACD − сигнал."""
    fast = df['close'].ewm(span=period, adjust=False).mean()
    slow = df['close'].ewm(span=2 * period + 2, adjust=False).mean()
    macd = fast - slow
    signal = macd.ewm(span=SIGNAL_PERIOD, adjust=False).mean()
    df = df.copy()
    df['k'] = macd - signal
    return df


def check_entry(prev_k, curr_k):
    if prev_k <= 0 < curr_k:
        return 'long'
    if prev_k >= 0 > curr_k:
        return 'short'
    return None


def check_exit(prev_k, curr_k, direction):
    if direction == 'long':
        return prev_k >= 0 > curr_k
    return prev_k <= 0 < curr_k


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_macd_line, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
