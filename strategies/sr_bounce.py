"""S/R bounce, каталог #110.

Сигнал: отскок от исторического уровня поддержки/сопротивления (rolling min/max).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, atr, state_entry, state_exit

TOL_MULT = 0.1


def calc_sr_bounce(df, period):
    """period — окно уровней. Колонка 'k' — состояние позиции."""
    res = df['high'].rolling(period, min_periods=period).max().shift(1)
    sup = df['low'].rolling(period, min_periods=period).min().shift(1)
    atr_v = atr(df, 14)
    tol = TOL_MULT * atr_v
    touched_sup = (df['low'] - sup).abs() <= tol
    touched_res = (df['high'] - res).abs() <= tol
    up = touched_sup & (df['close'] > df['open'])
    dn = touched_res & (df['close'] < df['open'])
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
    return run_backtest(df, calc_sr_bounce, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
