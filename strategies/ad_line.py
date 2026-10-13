"""Accumulation/Distribution line, каталог #93.

Сигнал: наклон сглаженной линии A/D пересекает ноль.
Standalone-модуль: не подключён к main/dispatcher.
Колонка 'k' — наклон A/D, value-cross нуля.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest


def calc_ad_line(df, period):
    """period — окно сглаживания A/D. Колонка 'k' — наклон."""
    rng = (df['high'] - df['low']).replace(0.0, np.nan)
    mfm = ((df['close'] - df['low']) - (df['high'] - df['close'])) / rng
    ad = (mfm.fillna(0.0) * df['volume']).cumsum()
    smooth = ad.ewm(span=period, adjust=False).mean()
    df = df.copy()
    df['k'] = smooth.diff().fillna(0.0)
    return df


def check_entry(prev_k, curr_k):
    if prev_k <= 0 < curr_k:
        return 'long'
    if prev_k >= 0 > curr_k:
        return 'short'
    return None


def check_exit(prev_k, curr_k, direction):
    if direction == 'long':
        return prev_k >= 0 > curr_k
    return prev_k <= 0 < curr_k


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_ad_line, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
