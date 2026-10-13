"""Triple EMA (10/20/50), каталог #39.

Сигнал: три EMA выстроены в одном направлении → LONG/SHORT.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_triple_ema(df, period):
    """period — быстрая EMA; средняя = 2·period, медленная = 5·period."""
    fast = df['close'].ewm(span=period, adjust=False).mean()
    mid = df['close'].ewm(span=2 * period, adjust=False).mean()
    slow = df['close'].ewm(span=5 * period, adjust=False).mean()
    up = (fast > mid) & (mid > slow)
    dn = (fast < mid) & (mid < slow)
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
    return run_backtest(df, calc_triple_ema, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
