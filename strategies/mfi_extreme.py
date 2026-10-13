"""MFI extreme (каталог #92).

Сигнал: Money Flow Index выходит из зон 20/80.
Standalone-модуль: не подключён к main/dispatcher.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest

OVERSOLD = 20
OVERBOUGHT = 80


def calc_mfi(df, period):
    """MFI(period): типичная цена × объём, ratio положит./отрицат. потока. Колонка 'k'."""
    tp = (df['high'] + df['low'] + df['close']) / 3.0
    mf = tp * df['volume']
    direction = tp.diff()
    pos_mf = mf.where(direction > 0, 0.0).rolling(period, min_periods=period).sum()
    neg_mf = mf.where(direction < 0, 0.0).rolling(period, min_periods=period).sum()
    ratio = pos_mf / neg_mf.replace(0.0, np.nan)
    mfi = 100.0 - 100.0 / (1.0 + ratio)
    df = df.copy()
    df['k'] = mfi.fillna(50.0)
    return df


def check_entry(prev_k, curr_k):
    if prev_k <= OVERSOLD and curr_k > OVERSOLD:
        return 'long'
    if prev_k >= OVERBOUGHT and curr_k < OVERBOUGHT:
        return 'short'
    return None


def check_exit(prev_k, curr_k, direction):
    if direction == 'long':
        return prev_k >= OVERBOUGHT and curr_k < OVERBOUGHT
    return prev_k <= OVERSOLD and curr_k > OVERSOLD


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_mfi, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
