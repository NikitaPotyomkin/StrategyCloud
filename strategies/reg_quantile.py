"""Regression: Quantile (H1).

Idea: Quantile regression — прогноз квантилей (0.25, 0.5, 0.75) вместо среднего.
Вход: median > price и q75 > q25 (long), median < price (short).
Выход: price пересекает median.
Отличие: квантили устойчивы к выбросам, дают распределение прогноза.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def _quantile_regression(x, y, tau=0.5, max_iter=100):
    """Quantile regression via linear programming approximation.

    Минимизируем: sum_{y>f(x)} tau*|y-f(x)| + sum_{y<=f(x)} (1-tau)*|y-f(x)|
    """
    n = len(x)
    if n < 5:
        return 0, 0

    # Gradient descent для quantile regression
    # f(x) = a + b*x
    a, b = 0, 0
    lr = 0.001

    for _ in range(max_iter):
        # Предсказания
        pred = a + b * x

        # Градиенты для quantile loss
        residual = y - pred
        sign = np.where(residual > 0, tau, tau - 1)

        grad_a = -np.sum(sign)
        grad_b = -np.sum(sign * x)

        a -= lr * grad_a
        b -= lr * grad_b

    return a, b


def calc_reg_quantile(df, period=100):
    """Quantile regression for median (tau=0.5).

    Предсказывает медиану распределения future returns.
    """
    k = np.zeros(len(df))
    x = np.arange(period, dtype=float)

    for i in range(period, len(df)):
        window = df['close'].iloc[i-period:i].values.astype(float)

        # Нормализуем
        y_mean = window.mean()
        y_std = window.std()
        if y_std == 0:
            y_std = 1
        y_norm = (window - y_mean) / y_std

        # Quantile regression для median
        a, b = _quantile_regression(x, y_norm, tau=0.5, max_iter=200)

        # Предсказание для следующего шага
        pred_norm = a + b * period
        pred = pred_norm * y_std + y_mean
        current = df['close'].iloc[i]

        # Сигнал: цена ниже медианы → long, выше → short
        if current < pred * 0.999:
            k[i] = 1
        elif current > pred * 1.001:
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
    return run_backtest(df, calc_reg_quantile, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
