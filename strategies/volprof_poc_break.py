"""Volume Profile: POC Break (H1).

Idea: 0081 volprof_poc_break
Вход: цена пробивает POC прошлого дня с объёмом > p70;
      выход: trail 2×ATR.
Отличие: POC (Point of Control) = цена с максимальным объёмом.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 4-12 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_volprof_poc_break(df, period=20):
    # POC proxy: typical price с максимальным накопленным объёмом
    typical = (df['high'] + df['low'] + df['close']) / 3

    # Volume-weighted typical price (VWAP proxy)
    vwap = (typical * df['volume']).rolling(period).sum() / df['volume'].rolling(period).sum()

    # POC = среднее значение vwap
    poc = vwap.rolling(period).mean()

    # Пробой POC
    breakout_up = df['close'] > poc
    breakout_down = df['close'] < poc

    # Объём подтверждает
    vol_p70 = df['volume'].rolling(period).quantile(0.70)
    high_vol = df['volume'] > vol_p70

    k = np.zeros(len(df))
    k[breakout_up & high_vol] = 1
    k[breakout_down & high_vol] = -1

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
    return run_backtest(df, calc_volprof_poc_break, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
