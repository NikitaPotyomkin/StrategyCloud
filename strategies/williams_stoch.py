"""Williams %R + Stochastic (согласованный сигнал), каталог #31.

Сигнал: оба осциллятора в одной зоне → LONG при перепроданности,
        SHORT при перекупленности.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

WR_OVERSOLD = -80.0
WR_OVERBOUGHT = -20.0
STOCH_OS = 20.0
STOCH_OB = 80.0


def calc_williams_stoch(df, period):
    """period — окно обоих осцилляторов. Колонка 'k' — состояние позиции."""
    high_max = df['high'].rolling(period, min_periods=period).max().shift(1)
    low_min = df['low'].rolling(period, min_periods=period).min().shift(1)
    rng = (high_max - low_min).replace(0.0, np.nan)
    wr = (-100.0 * (high_max - df['close']) / rng).fillna(-50.0)
    stoch = (100.0 * (df['close'] - low_min) / rng).fillna(50.0)
    up = (wr <= WR_OVERSOLD) & (stoch <= STOCH_OS)
    dn = (wr >= WR_OVERBOUGHT) & (stoch >= STOCH_OB)
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
    return run_backtest(df, calc_williams_stoch, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
