"""MA Ribbon expansion, каталог #43.

Сигнал: лента EMA выстроена в одном направлении И расходится шире среднего.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_ma_ribbon(df, period):
    """period — базовая EMA; лента: period, +10, +20, +30, +40."""
    spans = (period, period + 10, period + 20, period + 30, period + 40)
    emas = [df['close'].ewm(span=s, adjust=False).mean() for s in spans]
    stacked = pd.concat(emas, axis=1)
    spread = stacked.max(axis=1) - stacked.min(axis=1)
    expanding = spread > spread.rolling(period, min_periods=period).mean()
    up = (emas[0] > emas[1]) & (emas[1] > emas[2]) & (emas[2] > emas[3]) & (emas[3] > emas[4])
    dn = (emas[0] < emas[1]) & (emas[1] < emas[2]) & (emas[2] < emas[3]) & (emas[3] < emas[4])
    df = df.copy()
    df['k'] = np.where(up & expanding, 1, np.where(dn & expanding, -1, 0))
    return df


def check_entry(prev_s, curr_s):
    return state_entry(prev_s, curr_s)


def check_exit(prev_s, curr_s, direction):
    return state_exit(prev_s, curr_s, direction)


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_ma_ribbon, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
