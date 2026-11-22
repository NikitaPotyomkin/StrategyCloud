"""Statistical Test: Variance Ratio (H1).

Idea: 0484 stat_vr_ratio
Вход: variance ratio VR(5) > 1.2 (тренд);
      VR(5) < 0.8 (mean-reversion).
Выход: VR возвращается к 1.0.
Отличие: VR-тест проверяет random walk vs predictability.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 5-10 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_vr_ratio(df, period=10):
    ret = df['close'].pct_change().fillna(0)

    # Variance Ratio: VR(k) = Var(k)/Var(1) / k
    # При random walk VR = 1
    # VR > 1 -> тренд, VR < 1 -> mean-reversion

    k_periods = 5
    var_1 = ret.rolling(1).var()
    var_k = ret.rolling(k_periods).var()

    # VR
    vr = var_k / (k_periods * var_1.replace(0, np.nan).fillna(1))
    vr = vr.replace([np.inf, -np.inf], np.nan).fillna(1.0)

    # Скользящее среднее VR
    vr_mean = vr.rolling(period).mean()

    # Тренд: VR > 1.2, MR: VR < 0.8
    k = np.zeros(len(df))
    k[(vr_mean > 1.2) & (ret > 0)] = 1
    k[(vr_mean > 1.2) & (ret < 0)] = -1
    k[(vr_mean < 0.8) & (ret < 0)] = 1
    k[(vr_mean < 0.8) & (ret > 0)] = -1

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
    return run_backtest(df, calc_stat_vr_ratio, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
