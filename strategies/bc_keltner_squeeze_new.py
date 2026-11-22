"""Strategy: bc_keltner_squeeze (H1).

Idea: BB inside Keltner и "выстрел" — Keltner squeeze.
Вход: squeeze + breakout → signal.
Выход: ATR 2×.
Отличие: Keltner squeeze detection.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_bc_keltner_squeeze(df, period=20):
    """Keltner squeeze breakout.
    
    BB inside Keltner + breakout → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # BB
        bb_mid = np.mean(closes)
        bb_std = np.std(closes)
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        
        # Keltner
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_mean = atr.rolling(20).mean().iloc[i]
        kelt_upper = bb_mid + 2 * atr_mean
        kelt_lower = bb_mid - 2 * atr_mean
        
        # Squeeze: BB inside Keltner
        if bb_upper < kelt_upper and bb_lower > kelt_lower:
            # Breakout
            if closes[-1] > kelt_upper:
                k[i] = 1
            elif closes[-1] < kelt_lower:
                k[i] = -1
    
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
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
    return run_backtest(df, calc_bc_keltner_squeeze, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
