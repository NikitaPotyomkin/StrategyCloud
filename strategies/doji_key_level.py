"""Doji at key level, каталог #86.

Сигнал: доджи рядом с EMA(200) — отскок вверх от поддержки (LONG) или вниз от
сопротивления (SHORT).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, atr, state_entry, state_exit

EMA_PERIOD = 200
DOJI_BODY_MULT = 0.15
NEAR_MULT = 0.3


def calc_doji_key_level(df, period):
    """period — период ATR для допусков. Колонка 'k' — состояние позиции."""
    atr_v = atr(df, 14)
    body = (df['close'] - df['open']).abs()
    doji = body <= DOJI_BODY_MULT * atr_v
    ema = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    near = (df['close'] - ema).abs() <= NEAR_MULT * atr_v
    up = doji & near & (df['close'] < ema)
    dn = doji & near & (df['close'] > ema)
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
    return run_backtest(df, calc_doji_key_level, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
