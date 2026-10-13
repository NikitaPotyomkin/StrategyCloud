"""Volume-weighted MACD (VW-MACD), каталог #51.

Сигнал: VW-MACD пересекает сигнальную линию (вверх → LONG, вниз → SHORT).
Средние считаются по цене, взвешенной объёмом (EMA(close·vol)/EMA(vol)).
Standalone-модуль: не подключён к main/dispatcher.
Колонка 'k' — разность (VW-MACD − сигнал), value-cross нуля.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest

SIGNAL_PERIOD = 9


def _vw_price(df, span):
    """EMA цены, взвешенной объёмом."""
    vol = df['volume'].replace(0.0, np.nan).ffill().fillna(1.0)
    num = (df['close'] * vol).ewm(span=span, adjust=False).mean()
    den = vol.ewm(span=span, adjust=False).mean().replace(0.0, np.nan)
    return num / den


def calc_vw_macd(df, period):
    """period — быстрый период (медленный = 2·period + 2)."""
    vw_fast = _vw_price(df, period)
    vw_slow = _vw_price(df, 2 * period + 2)
    macd = vw_fast - vw_slow
    signal = macd.ewm(span=SIGNAL_PERIOD, adjust=False).mean()
    df = df.copy()
    df['k'] = (macd - signal).fillna(0.0)
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
    return run_backtest(df, calc_vw_macd, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
