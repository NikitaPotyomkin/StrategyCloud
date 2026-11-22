"""Regime Detection: Regime Duration Proxy (H1).

Idea: 0530 regime_duration
Вход: длительность текущего режима > p80 исторических режимов;
      вход по направлению текущего режима (знак скользящего среднего ret).
Выход: смена режима (возврат к среднему).
Отличие: отслеживает аномально длинные режимы для разворота.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 10-30 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_regime_duration(df, period=200):
    ret = df['close'].pct_change().fillna(0)
    atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
    atr = atr.replace(0, np.nan).fillna(df['close'].std() * 0.1)

    # Нормализованные ret
    norm_ret = ret / atr

    # Определяем режим: тренд вверх (> p60), тренд вниз (< p40), флэт
    p60 = norm_ret.rolling(period).quantile(0.60)
    p40 = norm_ret.rolling(period).quantile(0.40)

    regime = np.zeros(len(df))
    regime[norm_ret > p60] = 1
    regime[norm_ret < p40] = -1

    # Считаем длительность текущего режима
    duration = np.zeros(len(df))
    current_duration = 0
    current_regime = 0

    for i in range(len(df)):
        if regime[i] != current_regime:
            current_regime = regime[i]
            current_duration = 1
        else:
            current_duration += 1
        duration[i] = current_duration

    # p80 исторической длительности
    p80 = duration.rolling(period).quantile(0.80)
    p80 = p80.replace(0, np.nan).fillna(10)

    # Вход когда режим длинный
    k = np.zeros(len(df))
    k[duration > p80 & regime == 1] = 1
    k[duration > p80 & regime == -1] = -1

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
    return run_backtest(df, calc_regime_duration, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
