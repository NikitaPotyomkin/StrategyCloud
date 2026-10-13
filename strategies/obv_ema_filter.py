"""OBV + EMA, каталог #90.

Сигнал: OBV растёт при цене выше EMA(period); OBV падает при цене ниже EMA.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

EMA_PERIOD = 50


def _obv(df):
    direction = np.sign(df['close'].diff().fillna(0.0))
    return (direction * df['volume']).fillna(0.0).cumsum()


def calc_obv_ema(df, period):
    """period — окно сглаживания OBV. Колонка 'k' — состояние позиции."""
    obv = _obv(df)
    obv_slope = obv.ewm(span=period, adjust=False).mean().diff()
    ema = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    up = (obv_slope > 0) & (df['close'] > ema)
    dn = (obv_slope < 0) & (df['close'] < ema)
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
    return run_backtest(df, calc_obv_ema, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
