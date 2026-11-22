"""Structural: Equal Highs (H1).

Idea: 0127 struct_equal_highs
Вход: 2 равных максимума (equal highs) и пробой;
      выход: 10 баров.
Отличие: equal highs = ликвидность выше двойной вершины.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 5-15 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_equal_highs(df, period=20, tolerance=0.005):
    # Находим равные максимумы
    high_series = df['high']

    # Rolling max
    rolling_max = high_series.rolling(period).max()

    # Двойная вершина: цена возвращается к максимуму
    k = np.zeros(len(df))

    for i in range(period, len(df)):
        # Цена близка к rolling max (возврат к уровню)
        if abs(high_series.iloc[i] - rolling_max.iloc[i-1]) / rolling_max.iloc[i-1] < tolerance:
            # Пробой вверх
            if df['close'].iloc[i] > rolling_max.iloc[i-1]:
                k[i] = 1  # Long после пробоя
            # Ложный пробой (возврат)
            elif df['close'].iloc[i] < rolling_max.iloc[i-1] * 0.995:
                k[i] = -1  # Short после ложного пробоя

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
    return run_backtest(df, calc_struct_equal_highs, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
