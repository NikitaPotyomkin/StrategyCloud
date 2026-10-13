"""First Bar of Day, каталог #100.

Сигнал: вход в направлении первых `period` баров дня (действует до конца дня).
Требует DatetimeIndex; иначе день аппроксимируется группами по 24 бара.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def _day_keys(df):
    idx = df.index
    if isinstance(idx, pd.DatetimeIndex):
        return idx.normalize().to_numpy()
    return (np.arange(len(df)) // 24).astype(np.int64)


def calc_first_bar(df, period):
    """period — число первых баров дня, задающих направление (>=1). Колонка 'k'."""
    period = max(1, int(period))
    keys = _day_keys(df)
    open_ = df['open'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    n = len(df)
    state = np.zeros(n, dtype=int)

    cur_day = None
    day_dir = 0
    first_open = 0.0
    bars_in = 0
    for i in range(n):
        if keys[i] != cur_day:
            cur_day = keys[i]
            bars_in = 0
            day_dir = 0
            first_open = open_[i]
        bars_in += 1
        if bars_in == period:
            if close[i] > first_open:
                day_dir = 1
            elif close[i] < first_open:
                day_dir = -1
            else:
                day_dir = 0
        state[i] = day_dir

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
    return run_backtest(df, calc_first_bar, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
