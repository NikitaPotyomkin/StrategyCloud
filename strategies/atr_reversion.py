"""ATR Reversion, каталог #108.

Сигнал: отклонение цены от SMA(period) на ±k·ATR → возврат к среднему.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, atr, state_entry, state_exit

ATR_PERIOD = 14
ATR_MULT = 2.0


def calc_atr_reversion(df, period):
    """period — окно SMA. Колонка 'k' — состояние позиции."""
    sma = df['close'].rolling(period, min_periods=period).mean()
    atr_v = atr(df, ATR_PERIOD).fillna(0.0).replace(0.0, np.nan)
    dev = (df['close'] - sma) / atr_v
    up = dev < -ATR_MULT
    dn = dev > ATR_MULT
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
    return run_backtest(df, calc_atr_reversion, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
