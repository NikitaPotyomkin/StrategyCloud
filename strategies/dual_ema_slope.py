"""Dual EMA + slope filter, каталог #44.

Сигнал: EMA(period) выше/ниже EMA(2.5·period) при положительном/отрицательном
наклоне медленной EMA (period=20 → 20/50).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_dual_ema_slope(df, period):
    """period — быстрая EMA; медленная = 2.5·period."""
    fast = df['close'].ewm(span=period, adjust=False).mean()
    slow = df['close'].ewm(span=int(period * 2.5), adjust=False).mean()
    slope = slow.diff()
    up = (fast > slow) & (slope > 0)
    dn = (fast < slow) & (slope < 0)
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
    return run_backtest(df, calc_dual_ema_slope, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
