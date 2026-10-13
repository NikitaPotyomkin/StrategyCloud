"""MACD + EMA filter, каталог #49.

Сигнал: MACD выше/ниже сигнальной И цена выше/ниже EMA(50) → LONG/SHORT.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

SIGNAL_PERIOD = 9
EMA_PERIOD = 50


def calc_macd_ema(df, period):
    """period — быстрый период MACD (медленный = 2·period + 2)."""
    fast = df['close'].ewm(span=period, adjust=False).mean()
    slow = df['close'].ewm(span=2 * period + 2, adjust=False).mean()
    macd = fast - slow
    signal = macd.ewm(span=SIGNAL_PERIOD, adjust=False).mean()
    ema = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    up = (macd > signal) & (df['close'] > ema)
    dn = (macd < signal) & (df['close'] < ema)
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
    return run_backtest(df, calc_macd_ema, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
