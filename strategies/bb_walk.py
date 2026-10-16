"""Bollinger Band walk, каталог #54.

Сигнал: две свечи подряд закрываются за полосой (ход по полосе) → продолжение.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

STD_MULT = 2.0


def calc_bb_walk(df, period):
    """period — окно Bollinger. Колонка 'k' — состояние позиции."""
    ma = df['close'].rolling(period, min_periods=period).mean()
    sd = df['close'].rolling(period, min_periods=period).std(ddof=0).fillna(0.0)
    upper = ma + STD_MULT * sd
    lower = ma - STD_MULT * sd
    close = df['close']
    up = (close > upper) & (close.shift(1) > upper.shift(1))
    dn = (close < lower) & (close.shift(1) < lower.shift(1))
    # NOTE: BB Walk — корректно входить по close, т.к. стратегия требует 2
    # подряд закрытия за полосой (подтверждение, а не пробой).
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
    return run_backtest(df, calc_bb_walk, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
