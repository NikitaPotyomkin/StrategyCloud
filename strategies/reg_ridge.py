"""Regression: Ridge (L2 Regularized) (H1).

Idea: Ridge regression с L2-регуляризацией для мультиколлинеарных признаков.
Вход: прогнозы > thr (long) или < -thr (short).
Выход: прогноз меняет знак или пересекает 0.
Отличие: Ridge предотвращает overfitting через штраф на большие веса.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def _ridge_regression(X, y, alpha=1.0):
    """Ridge regression: solve (X^T X + alpha*I) w = X^T y."""
    n_features = X.shape[1]
    XtX = X.T @ X
    Xty = X.T @ y
    ridge = XtX + alpha * np.eye(n_features)
    try:
        w = np.linalg.solve(ridge, Xty)
    except np.linalg.LinAlgError:
        w = np.zeros(n_features)
    return w


def calc_reg_ridge(df, period=100, alpha=1.0):
    """Ridge regression with rolling window.

    Признаки: лаги ret(1-5), ATR-ratio, range, volume-ratio.
    """
    k = np.zeros(len(df))

    # Создаём признаки
    ret = df['close'].pct_change().fillna(0)
    atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
    atr_mean = atr.rolling(14).mean()
    atr_ratio = atr / atr_mean.replace(0, np.nan).fillna(1)
    hl_range = (df['high'] - df['low']) / df['close']
    vol_ratio = df['volume'] / df['volume'].rolling(20).mean().replace(0, np.nan).fillna(1)

    # Окно для признаков
    n_lags = 5

    for i in range(period, len(df)):
        # Собираем обучающую выборку
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

        # Ridge regression
        w = _ridge_regression(X_norm, y, alpha=alpha)
        # Прогноз для бара i — скалярным произведением, а не весом w[-1].
        # Строка признаков та же, что в обучении; берём j = i-4, чтобы целью был
        # ret[i+1]: признаки ret[i-3..i] уже известны на закрытии бара i.
        _jp = i - 4
        _f = [ret.iloc[_jp + lag] for lag in range(1, n_lags)]
        _f.append(atr_ratio.iloc[_jp] if not np.isnan(atr_ratio.iloc[_jp]) else 0.0)
        _f.append(float(hl_range.iloc[_jp]) if not np.isnan(hl_range.iloc[_jp]) else 0.0)
        _f.append(vol_ratio.iloc[_jp] if not np.isnan(vol_ratio.iloc[_jp]) else 0.0)
        x_now = (np.array(_f, dtype=float) - X_mean) / X_std
        prediction = float(x_now @ w) if len(w) else 0.0

        # Сигнал
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
    return run_backtest(df, calc_reg_ridge, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
