"""Regression: Theil-Sen Robust (H1).

Idea: Theil-Sen estimator — робастная регрессия, устойчивая к выбросам.
Вход: наклон > thr и цена выше линии (long), наклон < -thr и цена ниже (short).
Выход: наклон меняет знак или цена пересекает линию регрессии.
Отличие: Theil-Sen медиана всех парных наклонов, устойчив к pin bar и аномалиям.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_reg_theil_sen(df, period=50):
    """Theil-Sen robust regression estimator.

    Для каждого окна вычисляет медиану всех парных наклонов:
    slope_ij = (y_j - y_i) / (x_j - x_i) для всех i < j.
    """
    k = np.zeros(len(df))
    x = np.arange(period, dtype=float)

    for i in range(period, len(df)):
        window = df['close'].iloc[i-period:i].values.astype(float)

        # Вычисляем все парные наклоны
        slopes = []
        for j in range(1, period):
            for k_idx in range(j):
                denom = x[j] - x[k_idx]
                if abs(denom) < 1e-10:
                    continue
                slope = (window[j] - window[k_idx]) / denom
                slopes.append(slope)

        if len(slopes) == 0:
            continue

        # Медиана всех наклонов
        slope = np.median(slopes)
        intercept = np.median(window - slope * x)

        # Прогноз на следующий бар
        predicted = intercept + slope * period

        # Текущее значение
        current = df['close'].iloc[i]

        # Вход: наклон значимый и цена в направлении тренда
        if slope > 0 and current > predicted:
            k[i] = 1
        elif slope < 0 and current < predicted:
            k[i] = -1

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
    return run_backtest(df, calc_reg_theil_sen, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
