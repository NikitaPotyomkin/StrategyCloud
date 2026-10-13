"""MACD + RSI Combo, каталог #113.

Сигнал: кросс MACD/сигнальная И RSI в зоне тренда (RSI>50 для LONG, RSI<50 для SHORT).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
RSI_PERIOD = 14


def _rsi(close, period):
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def calc_macd_rsi(df, period):
    """period — период RSI. Колонка 'k' — состояние позиции."""
    fast = df['close'].ewm(span=MACD_FAST, adjust=False).mean()
    slow = df['close'].ewm(span=MACD_SLOW, adjust=False).mean()
    macd = fast - slow
    signal = macd.ewm(span=MACD_SIGNAL, adjust=False).mean()
    rsi = _rsi(df['close'], period)
    up = (macd > signal) & (rsi > 50.0)
    dn = (macd < signal) & (rsi < 50.0)
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
    return run_backtest(df, calc_macd_rsi, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
