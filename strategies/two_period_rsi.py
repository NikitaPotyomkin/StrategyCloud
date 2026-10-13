"""Two-period RSI (Connors), каталог #29.

Сигнал: RSI(2) < 10 при цене выше EMA(200) → LONG;
        RSI(2) > 90 при цене ниже EMA(200) → SHORT.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

OVERSOLD = 10
OVERBOUGHT = 90
TREND_PERIOD = 200


def _rsi(close, period):
    """RSI по Уайлдеру (EMA-сглаживание)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def calc_two_period_rsi(df, period):
    """period — период RSI (обычно 2). Колонка 'k' — состояние позиции."""
    rsi = _rsi(df['close'], period)
    trend = df['close'].ewm(span=TREND_PERIOD, adjust=False).mean()
    up = (rsi < OVERSOLD) & (df['close'] > trend)
    dn = (rsi > OVERBOUGHT) & (df['close'] < trend)
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
    return run_backtest(df, calc_two_period_rsi, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
