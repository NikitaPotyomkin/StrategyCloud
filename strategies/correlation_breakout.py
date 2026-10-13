"""Correlation breakout, каталог #20.

Сигнал: корреляция цена/объём пробивает N-барный максимум (при росте цены) или
минимум (при падении) → вход по направлению.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_correlation_breakout(df, period):
    """period — окно корреляции и экстремумов. Колонка 'k' — состояние позиции."""
    px = df['close'].pct_change()
    vol = df['volume'].replace(0.0, np.nan).ffill().fillna(1.0).pct_change()
    corr = px.rolling(period, min_periods=period).corr(vol).fillna(0.0)
    hi = corr.rolling(period, min_periods=period).max()
    lo = corr.rolling(period, min_periods=period).min()
    direction = np.sign(df['close'].diff().fillna(0.0))
    up = (corr >= hi) & (direction > 0)
    dn = (corr <= lo) & (direction < 0)
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
    return run_backtest(df, calc_correlation_breakout, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
