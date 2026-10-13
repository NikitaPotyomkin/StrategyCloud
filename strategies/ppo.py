"""Percentage Price Oscillator (PPO), каталог #36.

Сигнал: PPO пересекает сигнальную линию (вверх → LONG, вниз → SHORT).
Standalone-модуль: не подключён к main/dispatcher.
Колонка 'k' — разность (PPO − сигнал), value-cross нуля.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest

SIGNAL_PERIOD = 9


def calc_ppo(df, period):
    """period — быстрый период (медленный = 2·period). Колонка 'k' = PPO − сигнал."""
    fast = df['close'].ewm(span=period, adjust=False).mean()
    slow = df['close'].ewm(span=2 * period, adjust=False).mean()
    ppo = 100.0 * (fast - slow) / slow.replace(0.0, np.nan)
    signal = ppo.ewm(span=SIGNAL_PERIOD, adjust=False).mean()
    df = df.copy()
    df['k'] = (ppo - signal).fillna(0.0)
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
    return run_backtest(df, calc_ppo, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
