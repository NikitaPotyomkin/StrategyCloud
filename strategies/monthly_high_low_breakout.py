"""Monthly High/Low Breakout, каталог #97.

Сигнал: пробой максимума/минимума прошлого месяца с буфером 0.1·period·ATR(14).
Требует DatetimeIndex; иначе месяц аппроксимируется группами по 528 баров (≈22 торг. дня × 24).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, atr, state_entry, state_exit


def _month_keys(df):
    idx = df.index
    if isinstance(idx, pd.DatetimeIndex):
        return (idx.year.to_numpy() * 100 + idx.month.to_numpy())
    return (np.arange(len(df)) // 528).astype(np.int64)


def calc_monthly_breakout(df, period):
    """period — буфер пробоя в единицах 0.1·ATR(14). Колонка 'k'."""
    keys = _month_keys(df)
    atr_v = atr(df, 14).to_numpy(dtype=float)
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    n = len(df)
    state = np.zeros(n, dtype=int)

    prev_hi = prev_lo = None
    cur_hi = high[0]
    cur_lo = low[0]
    cur_key = keys[0]
    for i in range(n):
        if keys[i] != cur_key:
            prev_hi, prev_lo = cur_hi, cur_lo
            cur_key = keys[i]
            cur_hi, cur_lo = high[i], low[i]
        else:
            cur_hi = max(cur_hi, high[i])
            cur_lo = min(cur_lo, low[i])
        if prev_hi is None:
            continue
        buf = 0.1 * period * atr_v[i] if not np.isnan(atr_v[i]) else 0.0
        if close[i] > prev_hi + buf:
            state[i] = 1
        elif close[i] < prev_lo - buf:
            state[i] = -1

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
    return run_backtest(df, calc_monthly_breakout, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
