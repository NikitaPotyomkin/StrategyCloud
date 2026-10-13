"""Coin Flip + Trend Filter, каталог #105.

Сигнал: случайный вход (детерминированный seed) в направлении тренда EMA(period).
Служит базовой линией (benchmark): если стратегия не бьёт её — она бесполезна.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

SEED = 20260101


def calc_coin_flip(df, period):
    """period — окно EMA-фильтра тренда. Колонка 'k' — состояние позиции."""
    ema = df['close'].ewm(span=period, adjust=False).mean()
    rng = np.random.default_rng(SEED)
    coin = rng.choice([1, -1], size=len(df))
    trend_up = (df['close'] > ema).to_numpy()
    state = np.where(coin == 1, np.where(trend_up, 1, -1), 0)
    df = df.copy()
    df['k'] = state
    return df


def check_entry(prev_s, curr_s):
    return state_entry(prev_s, curr_s)


def check_exit(prev_s, curr_s, direction):
    return state_exit(prev_s, curr_s, direction)


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_coin_flip, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
