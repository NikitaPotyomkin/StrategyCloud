"""Stoch + RSI + EMA, каталог #117.

Сигнал: согласованный сигнал Stochastic и RSI при тренде EMA(200).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

EMA_PERIOD = 200
STOCH_OS = 20.0
STOCH_OB = 80.0
RSI_OS = 30.0
RSI_OB = 70.0


def _rsi(close, period):
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def calc_stoch_rsi_ema(df, period):
    """period — окно Stochastic/RSI. Колонка 'k' — состояние позиции."""
    low_min = df['low'].rolling(period, min_periods=period).min()
    high_max = df['high'].rolling(period, min_periods=period).max()
    rng = (high_max - low_min).replace(0.0, np.nan)
    stoch = (100.0 * (df['close'] - low_min) / rng).fillna(50.0)
    rsi = _rsi(df['close'], period)
    ema = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    up = (stoch < STOCH_OS) & (rsi < RSI_OS) & (df['close'] > ema)
    dn = (stoch > STOCH_OB) & (rsi > RSI_OB) & (df['close'] < ema)
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
    return run_backtest(df, calc_stoch_rsi_ema, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
