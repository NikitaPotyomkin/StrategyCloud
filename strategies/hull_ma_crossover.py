"""Hull MA crossover (смена наклона), каталог #41.

Сигнал: смена знака наклона Hull MA (вверх → LONG, вниз → SHORT).
Standalone-модуль: не подключён к main/dispatcher.
Колонка 'k' — наклон HMA (value-cross нуля).
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest


def _wma(series, n):
    """Взвешенная скользящая средняя (линейные веса)."""
    weights = np.arange(1, n + 1, dtype=float)
    wsum = weights.sum()
    return series.rolling(n, min_periods=n).apply(
        lambda x: float(np.dot(x, weights) / wsum), raw=True)


def calc_hull(df, period):
    """period — база HMA (полупериод и корень считаются автоматически)."""
    half = max(1, int(period / 2))
    root = max(1, int(np.sqrt(period)))
    hma = _wma(2.0 * _wma(df['close'], half) - _wma(df['close'], period), root)
    df = df.copy()
    df['k'] = hma.diff().fillna(0.0)
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
    return run_backtest(df, calc_hull, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
