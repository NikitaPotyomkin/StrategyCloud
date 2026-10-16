"""3 Crows / White Soldiers, каталог #85.

Сигнал: серия из N однонаправленных свечей с телом — White Soldiers → LONG,
Three Black Crows → SHORT.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, atr, state_entry, state_exit

MIN_BODY_MULT = 0.3


def calc_three_crows(df, period):
    """period — число свечей в серии. Колонка 'k' — состояние позиции."""
    atr_v = atr(df, 14)
    body = (df['close'] - df['open'])
    min_body = MIN_BODY_MULT * atr_v
    bull = body > min_body
    bear = body < -min_body
    # Проверка что ПОСЛЕДНИЕ period баров подряд удовлетворяют условию
    bull_run = bull.rolling(period, min_periods=period).sum()
    bear_run = bear.rolling(period, min_periods=period).sum()
    up = bull_run == period
    dn = bear_run == period
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
    return run_backtest(df, calc_three_crows, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
