"""Strategy: struct_ll_lh_chain (H1).

Idea: Цепочка LL+LH (спуск) — 3+ последовательных lower low + lower high.
Вход: спуск из 3+ LL+LH → продолжение short; первый HL → выход/разворот.
Выход: первый HL (для short) или LH (для long).
Отличие: цепочка LL/LH — мощный нисходящий сигнал, разворот при её нарушении.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_ll_lh_chain(df, period=20):
    """LL+LH chain detection (bearish descent pattern).
    
    Detects 3+ consecutive lower lows and lower highs.
    Signal on chain formation (short) or chain break (long).
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # Count consecutive LL+LH (bearish descent)
        ll_lh_count = 0
        for j in range(2, len(closes)):
            if closes[j] < closes[j-1] and highs[j] < highs[j-1] and lows[j] < lows[j-1]:
                ll_lh_count += 1
            else:
                ll_lh_count = 0
        
        # Count consecutive HH+HL (bullish stair)
        hh_hl_count = 0
        for j in range(2, len(closes)):
            if closes[j] > closes[j-1] and highs[j] > highs[j-1] and lows[j] > lows[j-1]:
                hh_hl_count += 1
            else:
                hh_hl_count = 0
        
        # Bearish chain: 3+ LL+LH
        if ll_lh_count >= 2:
            k[i] = -1
        # Bullish chain: 3+ HH+HL
        elif hh_hl_count >= 2:
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
    return run_backtest(df, calc_struct_ll_lh_chain, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
