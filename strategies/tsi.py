"""True Strength Index (TSI), каталог #33.

Сигнал: TSI пересекает нулевую линию (вверх → LONG, вниз → SHORT).
Standalone-модуль: не подключён к main/dispatcher.
Колонка 'k' — значение TSI (value-cross).
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest

SIGNAL_PERIOD = 13


def _double_ema(series, span):
    return series.ewm(span=span, adjust=False).mean().ewm(span=span, adjust=False).mean()


def calc_tsi(df, period):
    """period — длинное окно TSI. Колонка 'k' — значение TSI."""
    mom = df['close'].diff()
    num = _double_ema(mom, period)
    den = _double_ema(mom.abs(), period).replace(0.0, np.nan)
    tsi = 100.0 * num / den
    df = df.copy()
    df['k'] = tsi.fillna(0.0)
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
    return run_backtest(df, calc_tsi, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
