"""Strategy: struct_hh_hl_chain (H1).

Idea: Цепочка HH+HL (лестница вверх) — 3+ последовательных higher high + higher low.
Вход: лестница из 3+ HH+HL → продолжение long; первый LH → выход/разворот.
Выход: первый LH (для long) или HL (для short).
Отличие: цепочка HH/HL — мощный трендовый сигнал, разворот при её нарушении.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_hh_hl_chain(df, period=20):
    """HH+HL chain detection (bullish stair pattern).
    
    Detects 3+ consecutive higher highs and higher lows.
    Signal on chain formation (long) or chain break (short).
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # Count consecutive HH+HL
        hh_hl_count = 0
        for j in range(2, len(closes)):
            if closes[j] > closes[j-1] and highs[j] > highs[j-1] and lows[j] > lows[j-1]:
                hh_hl_count += 1
            else:
                hh_hl_count = 0
        
        # Count consecutive LL+LH (bearish)
        ll_lh_count = 0
        for j in range(2, len(closes)):
            if closes[j] < closes[j-1] and highs[j] < highs[j-1] and lows[j] < lows[j-1]:
                ll_lh_count += 1
            else:
                ll_lh_count = 0
        
        # Bullish chain: 3+ HH+HL
        if hh_hl_count >= 2:
            k[i] = 1
        # Bearish chain: 3+ LL+LH
        elif ll_lh_count >= 2:
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
    return run_backtest(df, calc_struct_hh_hl_chain, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
