"""Cycle Detection: Bandpass Filter 10-30 (H1).

Idea: 0735 cyc_bandpass
Вход: полосовой фильтр (10-30 баров) выше 0;
      выход когда фильтр ниже 0.
Отличие: bandpass выделяет только циклы 10-30 баров, отсекая шум и долгосрочный тренд.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 10-30 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_cyc_bandpass(df, period=20):
    close = df['close'].values.astype(float)

    # Lowpass (удаляем > 30 баров)
    lowpass = pd.Series(close).rolling(30).mean().values

    # Highpass (удаляем < 10 баров)
    highpass = pd.Series(close).rolling(10).mean().values

    # Bandpass = lowpass - highpass (остаются 10-30 баров)
    bandpass = lowpass - highpass

    # Сглаживание bandpass
    bandpass_smooth = pd.Series(bandpass).rolling(period).mean().values

    k = np.zeros(len(df))
    k[bandpass_smooth > 0] = 1
    k[bandpass_smooth < 0] = -1

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
    return run_backtest(df, calc_cyc_bandpass, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
