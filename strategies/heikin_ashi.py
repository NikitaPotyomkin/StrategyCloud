"""Heikin Ashi trend (каталог #119).

Сигнал: серия из N одноцветных HA-свечей (бычьих — LONG, медвежьих — SHORT).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 серия бычьих, -1 серия медвежьих, иначе 0.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_heikin_ashi(df, period):
    """period — длина серии HA. Колонка 'k' — состояние позиции."""
    ha_close = (df['open'] + df['high'] + df['low'] + df['close']) / 4.0
    ha_open = np.empty(len(df), dtype=float)
    ha_open[0] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2.0
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i - 1] + ha_close.iloc[i - 1]) / 2.0
    ha_open = pd.Series(ha_open, index=df.index)
    bull = ha_close > ha_open
    bear = ha_close < ha_open
    bull_run = bull.rolling(period, min_periods=period).sum()
    bear_run = bear.rolling(period, min_periods=period).sum()
    state = np.where(bull_run >= period, 1, np.where(bear_run >= period, -1, 0))
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
    return run_backtest(df, calc_heikin_ashi, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
