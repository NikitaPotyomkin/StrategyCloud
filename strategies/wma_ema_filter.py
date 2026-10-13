"""WMA + EMA filter, каталог #42.

Сигнал: WMA(period) пересекает EMA(50) — вход на кросс, тренд подтверждает EMA.
Standalone-модуль: не подключён к main/dispatcher.
Колонка 'k' — разность (WMA − EMA), value-cross нуля.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest

EMA_PERIOD = 50


def _wma(series, n):
    """Взвешенная скользящая средняя (линейные веса)."""
    weights = np.arange(1, n + 1, dtype=float)
    wsum = weights.sum()
    return series.rolling(n, min_periods=n).apply(
        lambda x: float(np.dot(x, weights) / wsum), raw=True)


def calc_wma_ema(df, period):
    """period — окно WMA. Колонка 'k' = WMA − EMA."""
    wma = _wma(df['close'], period)
    ema = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    df = df.copy()
    df['k'] = (wma - ema).fillna(0.0)
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
    return run_backtest(df, calc_wma_ema, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
