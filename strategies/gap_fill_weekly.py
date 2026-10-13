"""Gap Fill (weekly), каталог #101.

Сигнал: против гэпа пятница→понедельник, если он превышает 0.1·period·ATR(14)
(гэп вверх → SHORT, вниз → LONG).
Требует DatetimeIndex; иначе неделя аппроксимируется группами по 120 баров.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, atr, state_entry, state_exit


def _week_keys(df):
    idx = df.index
    if isinstance(idx, pd.DatetimeIndex):
        iso = idx.isocalendar()
        return (iso['year'].to_numpy() * 100 + iso['week'].to_numpy())
    return (np.arange(len(df)) // 120).astype(np.int64)


def calc_gap_fill(df, period):
    """period — минимальный размер гэпа в единицах 0.1·ATR(14). Колонка 'k'."""
    keys = _week_keys(df)
    atr_v = atr(df, 14).to_numpy(dtype=float)
    open_ = df['open'].to_numpy(dtype=float)
    close = df['close'].to_numpy(dtype=float)
    n = len(df)
    state = np.zeros(n, dtype=int)

    cur_key = keys[0]
    prev_close = None
    gap_dir = 0
    for i in range(n):
        if keys[i] != cur_key:
            cur_key = keys[i]
            if prev_close is not None:
                gap = open_[i] - prev_close
                thr = 0.1 * period * atr_v[i] if not np.isnan(atr_v[i]) else 0.0
                if gap > thr:
                    gap_dir = -1  # гэп вверх → шорт
                elif gap < -thr:
                    gap_dir = 1   # гэп вниз → лонг
                else:
                    gap_dir = 0
        state[i] = gap_dir
        prev_close = close[i]

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
    return run_backtest(df, calc_gap_fill, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
