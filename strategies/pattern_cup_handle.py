"""Strategy: pattern_cup_handle (H1).

Idea: Чашка с ручкой (Cup & Handle) — продолжение тренда.
Вход: пробой ручки вверх → long.
Выход: глубина чашки.
Отличие: классическая фигура продолжения с формальным детектом.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pattern_cup_handle(df, period=20):
    """Cup and Handle pattern detection.
    
    Detects cup (U-shaped recovery) + handle (small pullback).
    Handle breakout → long signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # Simple cup detection
        # Cup: high → low → high (U-shape)
        first_half = closes[:len(closes)//2]
        second_half = closes[len(closes)//2:]
        
        cup_low = np.min(closes)
        cup_start = closes[0]
        cup_end = closes[-1]
        
        # Check for U-shape (end near start)
        if cup_end > cup_low * 1.01 and cup_end < cup_start * 1.05:
            # Handle: small pullback near end
            handle_low = np.min(closes[-len(closes)//4:])
            handle_high = np.max(closes[-len(closes)//4:])
            
            # Handle should be in upper half of cup
            if handle_low > cup_low * 1.02:
                # Check for breakout
                if closes[-1] > handle_high:
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
    return run_backtest(df, calc_pattern_cup_handle, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
