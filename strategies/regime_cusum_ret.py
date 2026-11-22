"""Regime Detection: CUSUM accumulated returns (H1).

Idea: 0521 regime_cusum_ret
Вход: CUSUM накопленных ret пробивает +h (тренд вверх) или -h (тренд вниз);
      вход по знаку пробоя, выход когда CUSUM возвращается к 0.
Выход: CUSUM возвращается к 0 (смена импульса).
Отличие: CUSUM детектит накопленный дрейф цены, чувствителен к трендам.

Правка 12.11.2026: SL/TP ≥ 10 спредов, горизонт 4-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_regime_cusum_ret(df, period=100):
    """CUSUM accumulated returns regime detection.

    CUSUM = накопленная сумма ret (нормированных на ATR).
    Вход: CUSUM > +h (long) или CUSUM < -h (short).
    Выход: CUSUM возвращается к 0.
    """
    ret = df['close'].pct_change().fillna(0)
    atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
    atr = atr.replace(0, np.nan).fillna(df['close'].std() * 0.1)

    # Нормированные ret
    norm_ret = ret / atr
    # CUSUM накопление
    cusum = norm_ret.rolling(period).sum()

    # Пороги: h = 3 * std(norm_ret) * sqrt(period)
    h = 3 * norm_ret.rolling(period).std() * np.sqrt(period)
    h = h.replace(0, np.nan).fillna(0.5)

    k = np.zeros(len(df))
    k[cusum > h] = 1
    k[cusum < -h] = -1

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
    return run_backtest(df, calc_regime_cusum_ret, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
