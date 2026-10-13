"""Elder Impulse System, каталог #79.

Сигнал: «зелёный импульс» — EMA(period) растёт И гистограмма MACD растёт → LONG;
«красный» — обе падают → SHORT.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9


def calc_elder_impulse(df, period):
    """period — окно EMA. Колонка 'k' — состояние позиции."""
    ema = df['close'].ewm(span=period, adjust=False).mean()
    ema_up = ema.diff() > 0
    fast = df['close'].ewm(span=MACD_FAST, adjust=False).mean()
    slow = df['close'].ewm(span=MACD_SLOW, adjust=False).mean()
    macd = fast - slow
    hist = macd - macd.ewm(span=MACD_SIGNAL, adjust=False).mean()
    hist_up = hist.diff() > 0
    up = ema_up & hist_up
    dn = (~ema_up) & (~hist_up)
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
    return run_backtest(df, calc_elder_impulse, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
