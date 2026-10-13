"""Pearson Cross-asset correlation, каталог #16.

Сигнал: корреляция доходностей актива с референсом > 0.7 → вход по направлению
движения цены. Референс берётся из колонки 'ref_close' (мульти-актив); если её нет,
используется прокси — доходность объёма (NOTE ниже).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

CORR_THRESHOLD = 0.7


def calc_pearson_cross(df, period):
    """period — окно корреляции. Колонка 'k' — состояние позиции."""
    if 'ref_close' in df.columns:
        ref = df['ref_close'].astype(float)
    else:
        # NOTE: без внешнего индекса второй серией служит объём (прокси).
        ref = df['volume'].replace(0.0, np.nan).ffill().fillna(1.0)
    px_ret = df['close'].pct_change()
    ref_ret = ref.pct_change()
    corr = px_ret.rolling(period, min_periods=period).corr(ref_ret).fillna(0.0)
    direction = np.sign(df['close'].diff().fillna(0.0))
    state = np.where(corr > CORR_THRESHOLD, np.where(direction >= 0, 1, -1), 0)
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
    return run_backtest(df, calc_pearson_cross, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
