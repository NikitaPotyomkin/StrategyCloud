"""Regression: Polynomial (H1).

Idea: Полиномиальная регрессия степени 2-3 для выявления нелинейных трендов.
Вход: parabolic trajectory up (long) или down (short).
Выход: a2 меняет знак (разворот кривизны).
Отличие: polynomial улавливает ускорение/замедление тренда.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def _poly_fit_deg2(x, y):
    """Polynomial degree 2: y = a0 + a1*x + a2*x^2."""
    try:
        coeffs = np.polyfit(x, y, 2)
        return coeffs  # [a2, a1, a0]
    except np.linalg.LinAlgError:
        return np.array([0, 0, 0])


def calc_reg_polynomial(df, period=50):
    """Polynomial regression degree 2.

    a2 > 0: convex (ускорение вверх или замедление вниз)
    a2 < 0: concave (замедление вверх или ускорение вниз)
    """
    k = np.zeros(len(df))
    x = np.arange(period, dtype=float)

    for i in range(period, len(df)):
        window = df['close'].iloc[i-period:i].values.astype(float)

        coeffs = _poly_fit_deg2(x, window)
        a2, a1, a0 = coeffs

        # Прогноз на следующий бар
        predicted = a2 * period**2 + a1 * period + a0
        current = df['close'].iloc[i]

        # a2 > 0: convex → long если цена ниже параболы
        # a2 < 0: concave → short если цена выше параболы
        residual = current - predicted

        if a2 > 0.001 and residual < 0:
            k[i] = 1
        elif a2 < -0.001 and residual > 0:
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
    return run_backtest(df, calc_reg_polynomial, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
