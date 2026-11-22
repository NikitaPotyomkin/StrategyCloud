"""Cycle Detection: Hilbert Phase Zero-Cross (H1).

Idea: 0726 cyc_hilbert_phase
Вход: фаза Гильберта около 0 (начало цикла);
      выход когда фаза > 0.5*pi (середина цикла).
Отличие: Hilbert transform выделяет мгновенную фазу цикла.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 10-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_cyc_hilbert_phase(df, period=64):
    close = df['close'].values.astype(float)

    # Detrend
    close = close - pd.Series(close).rolling(20).mean().values

    # Hilbert transform (прямая аппроксимация через Hilbert quadrant)
    # I (in-phase): close smoothed
    I = pd.Series(close).rolling(period).mean().values

    # Q (quadrature): Hilbert transform approximation
    # Q = Hilbert(close) ≈ close shifted by quarter period
    q_shift = period // 4
    Q = np.zeros_like(close)
    Q[q_shift:] = (pd.Series(close).rolling(2).mean().diff(q_shift).values)
    Q[:q_shift] = 0

    # Фаза
    phase = np.arctan2(Q, I)

    # Нормализация в [0, pi]
    phase = np.abs(phase)

    k = np.zeros(len(df))

    # Фаза ~ 0 (начало цикла вверх)
    k[phase < 0.3] = 1

    # Фаза ~ pi (начало цикла вниз)
    k[phase > 2.8] = -1

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
    return run_backtest(df, calc_cyc_hilbert_phase, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
