"""Ichimoku + Chikou filter, каталог #70.

Сигнал: кросс Tenkan/Kijun подтверждён Chikou Span (цена выше/ниже значения N баров назад).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

KIJUN_PERIOD = 26


def calc_ichimoku_chikou(df, period):
    """period — окно Tenkan; Chikou-сдвиг = 26. Колонка 'k' — состояние позиции."""
    tenkan = ((df['high'].rolling(period, min_periods=period).max()
               + df['low'].rolling(period, min_periods=period).min()) / 2.0)
    kijun = ((df['high'].rolling(KIJUN_PERIOD, min_periods=KIJUN_PERIOD).max()
              + df['low'].rolling(KIJUN_PERIOD, min_periods=KIJUN_PERIOD).min()) / 2.0)
    chikou_ok_up = df['close'] > df['close'].shift(KIJUN_PERIOD)
    chikou_ok_dn = df['close'] < df['close'].shift(KIJUN_PERIOD)
    up = (tenkan > kijun) & chikou_ok_up
    dn = (tenkan < kijun) & chikou_ok_dn
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
    return run_backtest(df, calc_ichimoku_chikou, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
