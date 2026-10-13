"""Asian Session Breakout, каталог #98.

Сигнал: пробой максимума/минимума азиатской сессии длиной `period` часов.
Требует DatetimeIndex; иначе сессия аппроксимируется первыми `period` барами дня.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_asian_breakout(df, period):
    """period — длина азиатской сессии в часах (1..24). Колонка 'k'."""
    period = int(min(max(period, 1), 24))
    idx = df.index
    if isinstance(idx, pd.DatetimeIndex):
        days = idx.normalize().to_numpy()
        in_session = idx.hour.to_numpy() < period
    else:
        days = (np.arange(len(df)) // 24).astype(np.int64)
        in_session = (np.arange(len(df)) % 24) < period

    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    n = len(df)
    state = np.zeros(n, dtype=int)

    cur_day = None
    s_hi = -np.inf
    s_lo = np.inf
    ready = False
    for i in range(n):
        if days[i] != cur_day:
            cur_day = days[i]
            s_hi = -np.inf
            s_lo = np.inf
            ready = False
        if in_session[i]:
            s_hi = max(s_hi, high[i])
            s_lo = min(s_lo, low[i])
        elif s_hi > -np.inf:
            ready = True
        if ready:
            if close[i] > s_hi:
                state[i] = 1
            elif close[i] < s_lo:
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
    return run_backtest(df, calc_asian_breakout, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
