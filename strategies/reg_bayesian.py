"""Regression: Bayesian Linear (H1).

Idea: Bayesian linear regression с доверительными интервалами.
Вход: posterior mean > thr и CI не пересекает 0 (long/short).
Выход: CI начинает пересекать 0 (неопределённость).
Отличие: Bayesian даёт вероятностный прогноз с uncertainty.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def _bayesian_linear(x, y, prior_precision=0.01):
    """Bayesian linear regression with conjugate prior.

    Returns: (mean_pred, std_pred) для следующего шага.
    """
    n = len(x)
    if n < 5:
        return 0, 1

    # Добавляем intercept
    X = np.column_stack([np.ones(n), x])

    # Prior: w ~ N(0, prior_precision^-1 * I)
    # Posterior: w ~ N(mu, Sigma)
    # Sigma = (X^T X + prior_precision * I)^-1
    # mu = Sigma @ X^T @ y

    try:
        Sigma = np.linalg.inv(X.T @ X + prior_precision * np.eye(2))
        mu = Sigma @ X.T @ y
    except np.linalg.LinAlgError:
        return 0, 1

    # Prediction for x = n
    x_new = np.array([1, n])
    mean_pred = x_new @ mu

    # Prediction variance
    var_pred = x_new @ Sigma @ x_new

    return mean_pred, np.sqrt(var_pred)


def calc_reg_bayesian(df, period=100):
    """Bayesian linear regression.

    Использует posterior mean и CI для сигналов.
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

        mean_pred, std_pred = _bayesian_linear(x, y_norm, prior_precision=0.1)

        # Нормализованный прогноз
        z_score = mean_pred / (std_pred + 1e-10)

        # Сигнал: z > 2 (уверенный upward trend) или z < -2 (downward)
        if z_score > 2.0:
            k[i] = 1
        elif z_score < -2.0:
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
    return run_backtest(df, calc_reg_bayesian, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
