"""Range Breakout (daily), каталог #66.

Сигнал: пробой диапазона первых `period` баров торгового дня.
Требует DatetimeIndex; при его отсутствии день аппроксимируется группами по 24 бара.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def _day_keys(df):
    """Ключ дня для каждой свечи (дата либо номер группы по 24 бара)."""
    idx = df.index
    if isinstance(idx, pd.DatetimeIndex):
        return idx.normalize().to_numpy()
    return (np.arange(len(df)) // 24).astype(np.int64)


def calc_range_breakout(df, period):
    """period — число первых баров дня, задающих диапазон. Колонка 'k'."""
    keys = _day_keys(df)
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    n = len(df)
    state = np.zeros(n, dtype=int)

    cur_day = None
    bars_in_day = 0
    day_hi = -np.inf
    day_lo = np.inf
    ready = False
    for i in range(n):
        if keys[i] != cur_day:
            cur_day = keys[i]
            bars_in_day = 0
            day_hi = -np.inf
            day_lo = np.inf
            ready = False
        if bars_in_day < period:
            day_hi = max(day_hi, high[i])
            day_lo = min(day_lo, low[i])
        else:
            ready = True
        bars_in_day += 1
        if ready:
            if close[i] > day_hi:
                state[i] = 1
            elif close[i] < day_lo:
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
    return run_backtest(df, calc_range_breakout, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
