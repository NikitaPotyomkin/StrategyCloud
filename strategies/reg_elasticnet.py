"""Regression: ElasticNet (H1).

Idea: ElasticNet — комбинация L1 (Lasso) и L2 (Ridge) регуляризации.
Вход: прогноз > thr (long) или < -thr (short).
Выход: прогноз пересекает 0.
Отличие: ElasticNet лучше Ridge и Lasso по отдельности, автоматический отбор + stability.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def _elasticnet_coordinate_descent(X, y, alpha=0.1, l1_ratio=0.5, max_iter=1000, tol=1e-4):
    """ElasticNet через coordinate descent.

    ElasticNet loss = MSE/(2n) + alpha*l1*sum(|w|) + alpha*l2*(1-l1_ratio)/2*sum(w^2)
    """
    n_samples, n_features = X.shape
    w = np.zeros(n_features)

    for _ in range(max_iter):
        w_old = w.copy()

        for j in range(n_features):
            residual = y - X @ w + X[:, j] * w[j]
            x_j = X[:, j]

            rho = x_j @ residual / n_samples

            # Soft thresholding с elastic net penalty
            l1_penalty = alpha * l1_ratio
            l2_penalty = alpha * (1 - l1_ratio)

            denom = x_j @ x_j / n_samples + l2_penalty

            if denom < 1e-10:
                w[j] = 0
                continue

            if rho < -l1_penalty / 2:
                w[j] = (rho + l1_penalty / 2) / denom
            elif rho > l1_penalty / 2:
                w[j] = (rho - l1_penalty / 2) / denom
            else:
                w[j] = 0

        if np.max(np.abs(w - w_old)) < tol:
            break

    return w


def calc_reg_elasticnet(df, period=100, alpha=0.1, l1_ratio=0.5):
    """ElasticNet regression.

    Комбинация L1 (отбор признаков) и L2 (stability).
    """
    k = np.zeros(len(df))

    ret = df['close'].pct_change().fillna(0)
    atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
    atr_mean = atr.rolling(14).mean()
    atr_ratio = atr / atr_mean.replace(0, np.nan).fillna(1)
    hl_range = (df['high'] - df['low']) / df['close']
    vol_ratio = df['volume'] / df['volume'].rolling(20).mean().replace(0, np.nan).fillna(1)

    n_lags = 5

    for i in range(period, len(df)):
        X_list = []
        y_list = []

        for j in range(i - period, i - 5):
            if j < 0 or j >= len(df) - 1:
                continue

            features = []
            for lag in range(1, n_lags):   # лаг 5 — это цель (ret[j+5]), в признаки не берём
                features.append(ret.iloc[j + lag] if j + lag < len(df) else 0)
            features.append(atr_ratio.iloc[j] if not np.isnan(atr_ratio.iloc[j]) else 0)
            features.append(hl_range.iloc[j])
            features.append(vol_ratio.iloc[j] if not np.isnan(vol_ratio.iloc[j]) else 0)

            X_list.append(features)
            y_list.append(ret.iloc[j + 5])

        if len(X_list) < 30:
            continue

        X = np.array(X_list)
        y = np.array(y_list)

        # Нормализация
        X_mean = X.mean(axis=0)
        X_std = X.std(axis=0).copy(); X_std[X_std == 0] = np.nan; X_std = np.where(np.isnan(X_std), 1, X_std)
        X_norm = (X - X_mean) / X_std
        y_mean = y.mean()
        y_std = y.std()
        if y_std == 0:
            y_std = 1
        y_norm = (y - y_mean) / y_std

        # ElasticNet
        w = _elasticnet_coordinate_descent(X_norm, y_norm, alpha=alpha, l1_ratio=l1_ratio)

        # Прогноз для бара i — скалярным произведением, а не весом w[-1].
        # Цель в elasticnet нормирована (y_norm), поэтому возвращаем прогноз в
        # единицы доходности: * y_std + y_mean.
        _jp = i - 5
        _f = [ret.iloc[_jp + lag] for lag in range(1, n_lags)]
        _f.append(atr_ratio.iloc[_jp] if not np.isnan(atr_ratio.iloc[_jp]) else 0.0)
        _f.append(float(hl_range.iloc[_jp]) if not np.isnan(hl_range.iloc[_jp]) else 0.0)
        _f.append(vol_ratio.iloc[_jp] if not np.isnan(vol_ratio.iloc[_jp]) else 0.0)
        x_now = (np.array(_f, dtype=float) - X_mean) / X_std
        prediction = (float(x_now @ w) * y_std + y_mean) if len(w) else 0.0

        if prediction > 0.0002:
            k[i] = 1
        elif prediction < -0.0002:
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
    return run_backtest(df, calc_reg_elasticnet, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
