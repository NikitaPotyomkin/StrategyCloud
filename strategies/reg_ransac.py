"""Regression: RANSAC Robust (H1).

Idea: RANSAC (Random Sample Consensus) — робастная регрессия к выбросам.
Вход: RANSAC-линия > price (short) или < price (long).
Выход: цена пересекает RANSAC-линию.
Отличие: RANSAC игнорирует pin bar и аномалии, строит линию по инлайнерам.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def _ransac_regression(x, y, n_trials=50, threshold=0.005):
    """RANSAC linear regression.

    Возвращает (a, b) для y = a + b*x и mask инлайнеров.
    """
    n = len(x)
    best_inliers = 0
    best_a, best_b = 0, 0

    for _ in range(n_trials):
        # Случайные 2 точки
        idx = np.random.choice(n, 2, replace=False)
        x1, y1 = x[idx[0]], y[idx[0]]
        x2, y2 = x[idx[1]], y[idx[1]]

        if abs(x2 - x1) < 1e-10:
            continue

        b = (y2 - y1) / (x2 - x1)
        a = y1 - b * x1

        # Считаем инлайнеры
        predicted = a + b * x
        inliers = np.abs(y - predicted) < threshold

        if np.sum(inliers) > best_inliers:
            best_inliers = np.sum(inliers)
            best_a, best_b = a, b

    # Переобучение на лучших инлайнерах
    if best_inliers > 5:
        inliers_mask = np.abs(y - (best_a + best_b * x)) < threshold
        x_in = x[inliers_mask]
        y_in = y[inliers_mask]
        if len(x_in) > 2:
            try:
                coeffs = np.polyfit(x_in, y_in, 1)
                best_b = coeffs[0]
                best_a = coeffs[1]
            except Exception:
                pass

    return best_a, best_b


def calc_reg_ransac(df, period=100):
    """RANSAC robust regression.

    Игнорирует pin bar и аномалии, строит линию по большинству точек.
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

        a, b = _ransac_regression(x, y_norm, n_trials=50, threshold=0.1)

        # Прогноз
        predicted_norm = a + b * period
        predicted = predicted_norm * y_std + y_mean
        current = df['close'].iloc[i]

        # Цена ниже RANSAC-линии → long
        if current < predicted:
            k[i] = 1
        elif current > predicted:
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
    return run_backtest(df, calc_reg_ransac, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
