"""Detrended Price Oscillator (DPO), каталог #35.

Сигнал: DPO пересекает ноль (вверх → LONG, вниз → SHORT).
Standalone-модуль: не подключён к main/dispatcher.
Колонка 'k' — значение DPO (value-cross).
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest


def calc_dpo(df, period):
    """period — окно SMA. Колонка 'k' — значение DPO."""
    shift = int(period) // 2 + 1
    sma = df['close'].rolling(period, min_periods=period).mean().shift(shift)
    dpo = df['close'] - sma
    df = df.copy()
    df['k'] = dpo.fillna(0.0)
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
    return run_backtest(df, calc_dpo, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
