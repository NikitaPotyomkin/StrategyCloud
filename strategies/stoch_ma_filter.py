"""Stoch + MA filter, каталог #114.

Сигнал: сигнал Stochastic при цене выше/ниже SMA(100).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

SMA_PERIOD = 100
STOCH_OS = 20.0
STOCH_OB = 80.0


def calc_stoch_ma(df, period):
    """period — окно Stochastic. Колонка 'k' — состояние позиции."""
    low_min = df['low'].rolling(period, min_periods=period).min()
    high_max = df['high'].rolling(period, min_periods=period).max()
    rng = (high_max - low_min).replace(0.0, np.nan)
    k = (100.0 * (df['close'] - low_min) / rng).fillna(50.0)
    sma = df['close'].rolling(SMA_PERIOD, min_periods=SMA_PERIOD).mean()
    # Long: цена выше тренда + Stochastic перепродан → вход в рост
    up = (k < STOCH_OS) & (df['close'] > sma)
    # Short: цена ниже тренда + Stochastic перекуплен → вход в падение
    dn = (k > STOCH_OB) & (df['close'] < sma)
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
    return run_backtest(df, calc_stoch_ma, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
