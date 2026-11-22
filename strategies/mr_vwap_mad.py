"""Strategy: mr_vwap_mad (H1).

Idea: Deviation from VWAP > 2.5 MAD — возврат к VWAP.
Вход: отклонение от VWAP > 2.5 MAD → fade.
Выход: возврат к VWAP.
Отличие: VWAP + MAD (mean absolute deviation).

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_mr_vwap_mad(df, period=20):
    """Mean reversion to VWAP with MAD bands.
    
    Deviation from VWAP > 2.5 MAD → fade signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        volumes = df['volume'].iloc[i-period:i].values
        typical = (df['high'].iloc[i-period:i] + df['low'].iloc[i-period:i] + df['close'].iloc[i-period:i]) / 3
        
        # VWAP
        vwap = np.sum(typical.values * volumes) / np.sum(volumes)
        
        # MAD
        mad = np.mean(np.abs(typical.values - vwap))
        
        # Current deviation
        deviation = abs(closes[-1] - vwap)
        
        # Fade when deviation > 2.5 MAD
        if mad > 0 and deviation > 2.5 * mad:
            if closes[-1] > vwap:
                k[i] = -1
            else:
                k[i] = 1
    
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
    return run_backtest(df, calc_mr_vwap_mad, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
