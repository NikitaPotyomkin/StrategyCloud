"""Regime Detection: Markov Quantile Regime Switch (H1).

Idea: 0529 regime_markov_quantile
Вход: смена квантильного режима (Q1->Q4 по ret) - вход в тренд;
      Q1 (нижний квантиль) -> long, Q4 (верхний квантиль) -> short.
Выход: возврат в Q2/Q3 (нейтральная зона).
Отличие: Markov-цепь по квантилям ret детектит смену режима тренд/флэт.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 8-24 бара.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_regime_markov_quantile(df, period=60):
    ret = df['close'].pct_change().fillna(0)
    q25 = ret.rolling(period).quantile(0.25)
    q50 = ret.rolling(period).quantile(0.50)
    q75 = ret.rolling(period).quantile(0.75)

    curr_ret = ret.values
    curr_q25 = q25.values
    curr_q50 = q50.values
    curr_q75 = q75.values

    regime = np.zeros(len(df))
    for i in range(len(df)):
        if curr_q75[i] > 0 and curr_ret[i] >= curr_q75[i]:
            regime[i] = 4
        elif curr_q50[i] > 0 and curr_ret[i] >= curr_q50[i]:
            regime[i] = 2
        elif curr_q25[i] < 0 and curr_ret[i] <= curr_q25[i]:
            regime[i] = 1
        elif curr_ret[i] < curr_q50[i]:
            regime[i] = 3

    k = np.zeros(len(df))
    for i in range(1, len(df)):
        if regime[i-1] == 1 and regime[i] == 4:
            k[i] = 1
        elif regime[i-1] == 4 and regime[i] == 1:
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
    return run_backtest(df, calc_regime_markov_quantile, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
