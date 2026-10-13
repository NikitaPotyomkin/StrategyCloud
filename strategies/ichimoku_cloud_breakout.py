"""Ichimoku Cloud breakout, каталог #69.

Сигнал: цена закрытия выше/ниже облака (Senkou A/B).
Облако берётся без сдвига вперёд (без look-ahead).
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

TENKAN_PERIOD = 9
KIJUN_PERIOD = 26
SENKOU_B_PERIOD = 52


def calc_ichimoku_cloud(df, period):
    """period — окно Tenkan. Колонка 'k' — состояние позиции."""
    tenkan = ((df['high'].rolling(TENKAN_PERIOD, min_periods=TENKAN_PERIOD).max()
               + df['low'].rolling(TENKAN_PERIOD, min_periods=TENKAN_PERIOD).min()) / 2.0)
    kijun = ((df['high'].rolling(KIJUN_PERIOD, min_periods=KIJUN_PERIOD).max()
              + df['low'].rolling(KIJUN_PERIOD, min_periods=KIJUN_PERIOD).min()) / 2.0)
    senkou_a = (tenkan + kijun) / 2.0
    senkou_b = ((df['high'].rolling(SENKOU_B_PERIOD, min_periods=SENKOU_B_PERIOD).max()
                 + df['low'].rolling(SENKOU_B_PERIOD, min_periods=SENKOU_B_PERIOD).min()) / 2.0)
    cloud_top = pd.concat([senkou_a, senkou_b], axis=1).max(axis=1)
    cloud_bot = pd.concat([senkou_a, senkou_b], axis=1).min(axis=1)
    up = df['close'] > cloud_top
    dn = df['close'] < cloud_bot
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
    return run_backtest(df, calc_ichimoku_cloud, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
