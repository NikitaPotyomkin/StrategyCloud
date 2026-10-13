"""Keltner Channel breakout (каталог #58).

Сигнал: цена закрытия пробивает канал Кельтнера (EMA ± k·ATR).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 пробой вверх, -1 пробой вниз, 0 — внутри канала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, atr, state_entry, state_exit

EMA_PERIOD = 20
ATR_PERIOD = 10
K_MULT = 2.0


def calc_keltner(df, period):
    """period управляет EMA-базой. Колонка 'k' — состояние позиции."""
    ema = df['close'].ewm(span=period, adjust=False).mean()
    atr_v = atr(df, ATR_PERIOD)
    upper = ema + K_MULT * atr_v
    lower = ema - K_MULT * atr_v
    state = np.where(df['close'] > upper, 1, np.where(df['close'] < lower, -1, 0))
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
    return run_backtest(df, calc_keltner, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
