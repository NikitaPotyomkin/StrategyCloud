"""SuperTrend + EMA, каталог #64.

Сигнал: направление SuperTrend совпадает с положением цены относительно EMA(50).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, atr, state_entry, state_exit

ATR_PERIOD = 10
MULTIPLIER = 3.0
EMA_PERIOD = 50


def _supertrend_dir(df):
    """Направление SuperTrend: +1 вверх, -1 вниз."""
    hl2 = ((df['high'] + df['low']) / 2.0).to_numpy(dtype=float)
    atr_v = atr(df, ATR_PERIOD).fillna(0.0).to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    upper = hl2 + MULTIPLIER * atr_v
    lower = hl2 - MULTIPLIER * atr_v
    n = len(df)
    st = np.zeros(n)
    direction = np.ones(n)
    for i in range(n):
        if i == 0:
            st[i] = lower[i]
            direction[i] = 1
            continue
        direction[i] = 1 if close[i] > st[i - 1] else (-1 if close[i] < st[i - 1] else direction[i - 1])
        if direction[i] == 1:
            st[i] = max(lower[i], st[i - 1]) if direction[i - 1] == 1 else lower[i]
        else:
            st[i] = min(upper[i], st[i - 1]) if direction[i - 1] == -1 else upper[i]
    return direction


def calc_supertrend_ema(df, period):
    """period — окно EMA-фильтра. Колонка 'k' — состояние позиции."""
    direction = _supertrend_dir(df)
    ema = df['close'].ewm(span=period, adjust=False).mean().to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    up = (direction == 1) & (close > ema)
    dn = (direction == -1) & (close < ema)
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
    return run_backtest(df, calc_supertrend_ema, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
