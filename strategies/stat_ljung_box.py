"""Statistical Test: Ljung-Box Predictability (H1).

Idea: 0486 stat_ljung_box
Вход: Ljung-Box p < 0.05 по ret (предсказуемость);
      выход: p > 0.2 (случайность).
Отличие: LB-тест проверяет автокорреляцию ret.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 10-30 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_ljung_box(df, period=50):
    ret = df['close'].pct_change().fillna(0)

    # Простая аппроксимация Ljung-Box теста через ACF
    # LB = n*(n+2) * sum(acf(k)^2 / (n-k))
    # Если LB p-value < 0.05 -> есть автокорреляция -> предсказуемость

    # Используем ACF(1) как прокси
    acf_1 = ret.rolling(period).autocorr(freq=1)
    acf_1 = acf_1.fillna(0)

    # LB-статистика (упрощённо)
    n = period
    lb_stat = n * (n + 2) * (acf_1 ** 2) / n

    # p-value < 0.05 когда lb_stat > 3.84 (chi-squared 1 df)
    is_predictable = lb_stat > 3.84

    # Предсказуемость + направление
    k = np.zeros(len(df))
    k[is_predictable & (acf_1 > 0.2) & (ret > 0)] = 1
    k[is_predictable & (acf_1 > 0.2) & (ret < 0)] = -1
    k[is_predictable & (acf_1 < -0.2) & (ret < 0)] = 1
    k[is_predictable & (acf_1 < -0.2) & (ret > 0)] = -1

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
    return run_backtest(df, calc_stat_ljung_box, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
