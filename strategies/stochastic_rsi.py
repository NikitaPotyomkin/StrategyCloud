"""Stochastic RSI (каталог #30).

Сигнал: StochRSI(period) выходит из зон 20/80.
Standalone-модуль: не подключён к main/dispatcher.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest

OVERSOLD = 20
OVERBOUGHT = 80


def calc_stoch_rsi(df, period):
    """StochRSI = нормировка RSI в канале min/max за period. Колонка 'k'."""
    delta = df['close'].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)

    low_min = rsi.rolling(period, min_periods=period).min()
    high_max = rsi.rolling(period, min_periods=period).max()
    stoch = 100.0 * (rsi - low_min) / (high_max - low_min)
    stoch = stoch.replace([np.inf, -np.inf], np.nan).fillna(50.0)

    df = df.copy()
    df['k'] = stoch
    return df


def check_entry(prev_k, curr_k):
    if prev_k <= OVERSOLD and curr_k > OVERSOLD:
        return 'long'
    if prev_k >= OVERBOUGHT and curr_k < OVERBOUGHT:
        return 'short'
    return None


def check_exit(prev_k, curr_k, direction):
    if direction == 'long':
        return prev_k >= OVERBOUGHT and curr_k < OVERBOUGHT
    return prev_k <= OVERSOLD and curr_k > OVERSOLD


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_stoch_rsi, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
