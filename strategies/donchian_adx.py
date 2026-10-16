"""Donchian breakout + ADX filter (каталог #62).

Сигнал: пробой N-барного максимума/минимума при ADX > THRESHOLD.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 / -1 при валидном пробое, иначе 0.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, atr, state_entry, state_exit

ADX_PERIOD = 14
ADX_THRESHOLD = 25.0


def _adx(df, period):
    up = df['high'].diff()
    dn = -df['low'].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr_v = atr(df, period).replace(0.0, np.nan)
    plus_di = 100.0 * pd.Series(plus_dm, index=df.index).ewm(
        alpha=1.0 / period, min_periods=period, adjust=False).mean() / atr_v
    minus_di = 100.0 * pd.Series(minus_dm, index=df.index).ewm(
        alpha=1.0 / period, min_periods=period, adjust=False).mean() / atr_v
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean().fillna(0.0)


def calc_donchian_adx(df, period):
    """period — окно Donchian. Колонка 'k' — состояние позиции."""
    up = df['high'].rolling(period, min_periods=period).max().shift(1)
    dn = df['low'].rolling(period, min_periods=period).min().shift(1)
    adx = _adx(df, ADX_PERIOD)
    valid = adx > ADX_THRESHOLD
    state = np.where(valid & (df['high'] > up), 1,
                     np.where(valid & (df['low'] < dn), -1, 0))
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
    return run_backtest(df, calc_donchian_adx, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
