"""CCI extreme + trend, каталог #115.

Сигнал: CCI > 100 при тренде EMA(50) вверх → LONG; CCI < −100 при тренде вниз → SHORT.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

CCI_THRESHOLD = 100.0
EMA_PERIOD = 50


def calc_cci_extreme_trend(df, period):
    """period — окно CCI. Колонка 'k' — состояние позиции."""
    tp = (df['high'] + df['low'] + df['close']) / 3.0
    sma = tp.rolling(period, min_periods=period).mean()
    mad = tp.rolling(period, min_periods=period).apply(
        lambda x: float(np.mean(np.abs(x - np.mean(x)))), raw=True).replace(0.0, np.nan)
    cci = (tp - sma) / (0.015 * mad)
    cci = cci.fillna(0.0)
    ema = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    trend_up = df['close'] > ema
    up = (cci > CCI_THRESHOLD) & trend_up
    dn = (cci < -CCI_THRESHOLD) & (~trend_up)
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
    return run_backtest(df, calc_cci_extreme_trend, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
