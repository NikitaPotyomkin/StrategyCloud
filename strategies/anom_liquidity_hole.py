"""Anomaly Detection: Liquidity Hole (H1).

Idea: 0922 anom_liquidity_hole
Вход: диапазон бара > 5×ATR при объёме < p20;
      выход через 3 бара (пауза после аномалии).
Отличие: liquidity hole = резкий выброс цены на тонком объёме.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 3-8 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_anom_liquidity_hole(df, period=100):
    atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
    atr = atr.replace(0, np.nan).fillna(df['close'].std() * 0.1)

    bar_range = df['high'] - df['low']

    # Объём p20
    vol_p20 = df['volume'].rolling(period).quantile(0.20)

    # Аномалия: range > 5×ATR и объём < p20
    is_anomaly = (bar_range > 5 * atr) & (df['volume'] < vol_p20)

    # Направление: close в верхней/нижней трети
    k = np.zeros(len(df))
    k[(is_anomaly) & (df['close'] > df['open'])] = -1  # Длинная тень вверх -> fade
    k[(is_anomaly) & (df['close'] < df['open'])] = 1   # Длинная тень вниз -> fade

    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Returns 'long' / 'short' / None for engine run_backtest
    if prev == 0 and curr == 1:
        return 'long'
    if prev == 0 and curr == -1:
        return 'short'
    return None


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    return run_backtest(df, calc_anom_liquidity_hole, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
