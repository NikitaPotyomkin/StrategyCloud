"""OBV slope, каталог #89.

Сигнал: устойчивый наклон OBV (сглаженный) пересекает ноль.
Standalone-модуль: не подключён к main/dispatcher.
Колонка 'k' — наклон сглаженного OBV, value-cross нуля.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest


def _obv(df):
    direction = np.sign(df['close'].diff().fillna(0.0))
    return (direction * df['volume']).fillna(0.0).cumsum()


def calc_obv_slope(df, period):
    """period — окно сглаживания OBV. Колонка 'k' — наклон."""
    obv = _obv(df)
    smooth = obv.ewm(span=period, adjust=False).mean()
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
    return run_backtest(df, calc_obv_slope, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
