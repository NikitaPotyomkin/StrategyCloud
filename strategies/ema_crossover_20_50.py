"""EMA Crossover (20/50), каталог #40.

Сигнал: EMA(period) пересекает EMA(2.5·period) — при period=20 это 20/50.
Standalone-модуль: не подключён к main/dispatcher.
Колонка 'k' — разность (быстрая − медленная), value-cross нуля.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest


def calc_ema_cross(df, period):
    """period — быстрая EMA. Колонка 'k' = fast − slow."""
    fast = df['close'].ewm(span=period, adjust=False).mean()
    slow = df['close'].ewm(span=int(period * 2.5), adjust=False).mean()
    df = df.copy()
    df['k'] = fast - slow
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
    return run_backtest(df, calc_ema_cross, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
