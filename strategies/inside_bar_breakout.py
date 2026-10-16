"""Inside Bar Breakout (каталог #83).

Сигнал: внутри материнской свечи формируется Inside Bar, затем пробой её границ.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 пробой вверх материнской свечи, -1 вниз, иначе 0.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_inside_bar(df, period):
    """period — минимальная «жизнь» материнской свечи (не обязателен). Колонка 'k'."""
    mother_high = df['high'].shift(1)
    mother_low = df['low'].shift(1)
    is_inside = (df['high'] < mother_high) & (df['low'] > mother_low)
    # Сигнал берём на баре ПОСЛЕ inside bar (пробой границ материнской свечи).
    mother_high_prev = df['high'].shift(2)
    mother_low_prev = df['low'].shift(2)
    inside_prev = ((df['high'].shift(1) < mother_high_prev) &
                   (df['low'].shift(1) > mother_low_prev))
    state = np.where(inside_prev & (df['high'] > mother_high_prev), 1,
                     np.where(inside_prev & (df['low'] < mother_low_prev), -1, 0))
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
    return run_backtest(df, calc_inside_bar, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
