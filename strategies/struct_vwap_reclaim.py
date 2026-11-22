"""Strategy: struct_vwap_reclaim (H1).

Idea: Возврат цены выше дневного VWAP после пробоя вниз — VWAP reclaim.
Вход: reclaim VWAP → signal.
Выход: 2SD up.
Отличие: VWAP reclaim as institutional signal.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_vwap_reclaim(df, period=20):
    """VWAP reclaim detection.
    
    Price reclaims daily VWAP after breakdown → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        volumes = df['volume'].iloc[i-period:i].values
        typical = (df['high'].iloc[i-period:i] + df['low'].iloc[i-period:i] + df['close'].iloc[i-period:i]) / 3
        
        # VWAP
        vwap = np.sum(typical.values * volumes) / np.sum(volumes)
        
        # Reclaim
        if i > 1:
            prev_close = closes[-2]
            if prev_close < vwap and closes[-1] > vwap:
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
    return run_backtest(df, calc_struct_vwap_reclaim, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
