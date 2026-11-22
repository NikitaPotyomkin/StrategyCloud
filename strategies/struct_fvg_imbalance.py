"""Structural: Fair Value Gap / Imbalance (H1).

Idea: 0125 struct_fvg_imbalance
Вход: цена возвращается в Fair Value Gap (незакрытый разрыв);
      выход: закрытие FVG.
Отличие: FVG = трёхсвечный паттерн с пробелом между телами.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 3-8 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_fvg_imbalance(df, period=3):
    # FVG: разрыв между телами свечей
    # Bullish FVG: low[i-2] > high[i] (разрыв вниз)
    # Bearish FVG: high[i-2] < low[i] (разрыв вверх)

    k = np.zeros(len(df))

    for i in range(2, len(df)):
        # Bullish FVG (разрыв вниз) -> цена должна вернуться вниз к FVG
        if df['low'].iloc[i-2] > df['high'].iloc[i]:
            fvg_low = df['high'].iloc[i]
            fvg_high = df['low'].iloc[i-2]
            # Цена возвращается в FVG
            if fvg_low <= df['close'].iloc[i] <= fvg_high:
                k[i] = 1  # Long от нижней границы FVG

        # Bearish FVG (разрыв вверх)
        if df['high'].iloc[i-2] < df['low'].iloc[i]:
            fvg_low = df['high'].iloc[i-2]
            fvg_high = df['low'].iloc[i]
            # Цена возвращается в FVG
            if fvg_low <= df['close'].iloc[i] <= fvg_high:
                k[i] = -1  # Short от верхней границы FVG

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
    return run_backtest(df, calc_struct_fvg_imbalance, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
