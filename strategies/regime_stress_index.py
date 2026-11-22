"""Regime Detection: Stress Index Composite (H1).

Idea: 0544 regime_stress_index
Вход: композитный индекс стресса (vol + spread + corr) > p80;
      вход против стресса (fade экстремума).
Выход: индекс стресса < p50 (нормализация).
Отличие: стресс-индекс объединяет волатильность, спред и корреляцию.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 4-12 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_regime_stress_index(df, period=100):
    ret = df['close'].pct_change().fillna(0)
    atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
    atr = atr.replace(0, np.nan).fillna(df['close'].std() * 0.1)

    # Компонента 1: волатильность (ATR z-score)
    atr_mean = atr.rolling(period).mean()
    atr_std = atr.rolling(period).std()
    vol_z = (atr - atr_mean) / atr_std.replace(0, np.nan).fillna(1)

    # Компонента 2: размер бара (range z-score)
    bar_range = (df['high'] - df['low']) / df['close']
    range_mean = bar_range.rolling(period).mean()
    range_std = bar_range.rolling(period).std()
    range_z = (bar_range - range_mean) / range_std.replace(0, np.nan).fillna(1)

    # Компонента 3: ускорение ret (второй порядок)
    ret_accel = ret.diff().diff()
    accel_z = ret_accel.rolling(period).mean() / ret_accel.rolling(period).std().replace(0, np.nan).fillna(1)

    # Композитный индекс стресса
    stress = (vol_z.abs() + range_z.abs() + accel_z.abs()) / 3
    stress = stress.fillna(0)

    # Пороги
    p80 = stress.rolling(period).quantile(0.80)
    p50 = stress.rolling(period).quantile(0.50)

    # Вход против стресса (fade)
    k = np.zeros(len(df))
    k[stress > p80 & ret > 0] = -1  # Стресс вверх -> short
    k[stress > p80 & ret < 0] = 1   # Стресс вниз -> long

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
    return run_backtest(df, calc_regime_stress_index, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
