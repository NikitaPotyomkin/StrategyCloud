"""Rolling covariance matrix break, каталог #21.

Сигнал: норма Фробениуса скользящей ковариационной матрицы признаков
(доходность, объём, размах) отклоняется > 2σ → вход по направлению движения.
Векторизовано (sliding_window_view + einsum) — без поштучного цикла по барам.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

Z_THRESHOLD = 2.0


def calc_covariance_break(df, period):
    """period — окно ковариации. Колонка 'k' — состояние позиции."""
    period = max(2, int(period))
    r = df['close'].pct_change().fillna(0.0).to_numpy(dtype=float)
    v = df['volume'].replace(0.0, np.nan).ffill().fillna(1.0).pct_change().fillna(0.0).to_numpy(dtype=float)
    g = ((df['high'] - df['low']) / df['close'].replace(0.0, np.nan)).fillna(0.0).to_numpy(dtype=float)
    feats = np.vstack([r, v, g])                                           # (3, n)

    n = feats.shape[1]
    norm = np.zeros(n)
    if n >= period:
        win = np.lib.stride_tricks.sliding_window_view(feats, period, axis=1)  # (3, N, period)
        win = win.transpose(1, 0, 2)                                           # (N, 3, period)
        wc = win - win.mean(axis=2, keepdims=True)
        cov = np.einsum('ncp,nkq->npq', wc, wc) / (period - 1)                 # (N, 3, 3)
        norm[period - 1:] = np.sqrt((cov ** 2).sum(axis=(1, 2)))

    norm_s = pd.Series(norm, index=df.index)
    mean = norm_s.rolling(period, min_periods=period).mean()
    std = norm_s.rolling(period, min_periods=period).std(ddof=0).replace(0.0, np.nan)
    z = ((norm_s - mean) / std).fillna(0.0)

    direction = np.sign(df['close'].diff().fillna(0.0))
    df = df.copy()
    df['k'] = np.where(z > Z_THRESHOLD, np.where(direction >= 0, 1, -1), 0)
    return df


def check_entry(prev_s, curr_s):
    return state_entry(prev_s, curr_s)


def check_exit(prev_s, curr_s, direction):
    return state_exit(prev_s, curr_s, direction)


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_covariance_break, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
