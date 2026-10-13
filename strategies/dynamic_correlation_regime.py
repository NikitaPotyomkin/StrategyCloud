"""Dynamic correlation regime, каталог #19.

Сигнал: короткая корреляция цена/объём выше длинной (режим усиливается)
→ вход по направлению движения.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_dynamic_corr(df, period):
    """period — короткое окно; длинное = 2·period. Колонка 'k' — состояние позиции."""
    px = df['close'].pct_change()
    vol = df['volume'].replace(0.0, np.nan).ffill().fillna(1.0).pct_change()
    short = px.rolling(period, min_periods=period).corr(vol)
    long = px.rolling(2 * period, min_periods=period).corr(vol)
    regime = (short - long).fillna(0.0)
    direction = np.sign(df['close'].diff().fillna(0.0))
    state = np.where(regime > 0, np.where(direction >= 0, 1, -1), 0)
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
    return run_backtest(df, calc_dynamic_corr, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
