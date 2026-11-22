"""Cycle Detection: Wavelet Energy Level (H1).

Idea: 0724 cyc_wavelet_energy
Вход: энергия wavelet уровня 3 (db4) выше уровней 1-2;
      выход когда энергия инвертируется.
Отличие: wavelet-декомпозиция выделяет мультишкальные циклы.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 10-30 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_cyc_wavelet_energy(df, period=100):
    close = df['close'].values.astype(float)

    # Detrend
    close = close - np.mean(close)

    # Простая wavelet-декомпозиция (moving average filters)
    # Level 1: MA(4)
    ma4 = pd.Series(close).rolling(4).mean().values
    level1 = close - ma4
    level1 = np.nan_to_num(level1, nan=0.0)

    # Level 2: MA(8)
    ma8 = pd.Series(close).rolling(8).mean().values
    level2 = close - ma8
    level2 = np.nan_to_num(level2, nan=0.0)

    # Level 3: MA(16)
    ma16 = pd.Series(close).rolling(16).mean().values
    level3 = close - ma16
    level3 = np.nan_to_num(level3, nan=0.0)

    # Энергия (abs) каждого уровня
    energy1 = np.abs(level1)
    energy2 = np.abs(level2)
    energy3 = np.abs(level3)

    # Средние энергии за period
    e1_mean = pd.Series(energy1).rolling(period).mean().values
    e2_mean = pd.Series(energy2).rolling(period).mean().values
    e3_mean = pd.Series(energy3).rolling(period).mean().values

    # E3 > E1 и E3 > E2
    k = np.zeros(len(df))
    k[energy3 > e3_mean & energy3 > energy1 & energy3 > energy2] = 1
    k[energy3 < e3_mean & energy3 < energy1 & energy3 < energy2] = -1

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
    return run_backtest(df, calc_cyc_wavelet_energy, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
