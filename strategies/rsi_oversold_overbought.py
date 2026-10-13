"""RSI oversold/overbought (каталог #27).

Сигнал: RSI(period) пересекает снизу 30 (LONG) или сверху 70 (SHORT).
Standalone-модуль: не подключён к main/dispatcher.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest

OVERSOLD = 30
OVERBOUGHT = 70


def calc_rsi(df, period):
    """RSI по Уайлдеру (EMA-сглаживание). Колонка сигнала — 'k'."""
    delta = df['close'].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    df = df.copy()
    df['k'] = rsi.fillna(50.0)
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
    return run_backtest(df, calc_rsi, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
