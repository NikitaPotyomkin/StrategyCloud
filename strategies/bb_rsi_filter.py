"""Bollinger breakout + RSI filter, каталог #55.

Сигнал: пробой полосы BB при RSI в зоне тренда (RSI>50 для LONG, RSI<50 для SHORT).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

STD_MULT = 2.0
RSI_PERIOD = 14


def _rsi(close, period):
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def calc_bb_rsi(df, period):
    """period — окно Bollinger. Колонка 'k' — состояние позиции."""
    ma = df['close'].rolling(period, min_periods=period).mean()
    sd = df['close'].rolling(period, min_periods=period).std(ddof=0).fillna(0.0)
    upper = ma + STD_MULT * sd
    lower = ma - STD_MULT * sd
    rsi = _rsi(df['close'], RSI_PERIOD)
    up = (df['high'] > upper) & (rsi > 50.0)
    dn = (df['low'] < lower) & (rsi < 50.0)
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
    return run_backtest(df, calc_bb_rsi, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
