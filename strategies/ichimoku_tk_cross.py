"""Ichimoku Tenkan/Kijun cross, каталог #68.

Сигнал: Tenkan пересекает Kijun (вверх → LONG, вниз → SHORT).
Standalone-модуль: не подключён к main/dispatcher.
Колонка 'k' — разность (Tenkan − Kijun), value-cross нуля.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest

KIJUN_PERIOD = 26


def calc_ichimoku_tk(df, period):
    """period — окно Tenkan; Kijun = 26. Колонка 'k' = Tenkan − Kijun."""
    tenkan = ((df['high'].rolling(period, min_periods=period).max()
               + df['low'].rolling(period, min_periods=period).min()) / 2.0)
    kijun = ((df['high'].rolling(KIJUN_PERIOD, min_periods=KIJUN_PERIOD).max()
              + df['low'].rolling(KIJUN_PERIOD, min_periods=KIJUN_PERIOD).min()) / 2.0)
    df = df.copy()
    df['k'] = tenkan - kijun
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
    return run_backtest(df, calc_ichimoku_tk, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
