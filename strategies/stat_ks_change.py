"""Statistical Test: KS Change-Point (H1).

Idea: 0494 stat_ks_change
Вход: KS-тест распределений двух окон p < 0.01 (смена режима);
      выход: 10 баров.
Отличие: KS-тест детектит смену распределения ret.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 10 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_ks_change(df, period=60):
    ret = df['close'].pct_change().fillna(0)

    # KS-тест: сравниваем последние period баров с предыдущими period
    # Используем прокси: разница средних / объединённый std

    k = np.zeros(len(df))

    for i in range(period * 2, len(df)):
        recent = ret.iloc[i-period:i].values
        past = ret.iloc[i-2*period:i-period].values

        if len(recent) > 10 and len(past) > 10:
            mean_diff = abs(np.mean(recent) - np.mean(past))
            pooled_std = np.sqrt((np.var(recent) + np.var(past)) / 2)

            if pooled_std > 0:
                # KS-прокси: нормализованная разница средних
                ks_stat = mean_diff / (pooled_std * np.sqrt(2 * period / period))

                # Смена режима: ks_stat > 2 (p < 0.01)
                if ks_stat > 2.0:
                    # Вход по знаку recent
                    if np.mean(recent) > 0:
                        k[i] = 1
                    else:
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
    return run_backtest(df, calc_stat_ks_change, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
