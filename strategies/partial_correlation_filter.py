"""Partial correlation filter, каталог #18.

Сигнал: частная корреляция цены с объёмом при контроле волатильности > порога
→ вход по направлению движения.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

PARTIAL_THRESHOLD = 0.3


def calc_partial_correlation(df, period):
    """period — окно корреляций. Колонка 'k' — состояние позиции."""
    px = df['close'].pct_change()
    vol = df['volume'].replace(0.0, np.nan).ffill().fillna(1.0).pct_change()
    vola = px.abs()
    r_xy = px.rolling(period, min_periods=period).corr(vol)
    r_xz = px.rolling(period, min_periods=period).corr(vola)
    r_yz = vol.rolling(period, min_periods=period).corr(vola)
    denom = np.sqrt((1.0 - r_xz ** 2) * (1.0 - r_yz ** 2)).replace(0.0, np.nan)
    partial = ((r_xy - r_xz * r_yz) / denom).fillna(0.0)
    direction = np.sign(df['close'].diff().fillna(0.0))
    state = np.where(partial > PARTIAL_THRESHOLD, np.where(direction >= 0, 1, -1), 0)
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
    return run_backtest(df, calc_partial_correlation, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
