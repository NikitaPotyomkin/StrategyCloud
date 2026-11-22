"""Strategy: pattern_hns_top (H1).

Idea: Голова и плечи (H&S) — разворотная фигура.
Вход: пробой neckline вниз → short.
Выход: высота головы.
Отличие: классическая разворотная фигура с формальным детектом.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pattern_hns_top(df, period=20):
    """Head and Shoulders top detection.
    
    Detects H&S pattern (left shoulder, head, right shoulder).
    Neckline breakdown → short signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Simple H&S detection
        # Divide into 3 sections
        section_size = len(highs) // 3
        
        if section_size < 3:
            continue
        
        # Find peaks in each section
        left_high = np.max(highs[:section_size])
        mid_high = np.max(highs[section_size:2*section_size])
        right_high = np.max(highs[2*section_size:])
        
        # Head should be highest, shoulders lower and similar
        if mid_high > left_high and mid_high > right_high:
            if abs(left_high - right_high) < 0.005 * mid_high:
                # Neckline (support between shoulders)
                neckline = min(left_high, right_high)
                
                # Check for breakdown
                if closes[-1] < neckline:
                    k[i] = -1
        
        # Inverse H&S (bullish)
        section_lows = [np.min(lows[:section_size]), np.min(lows[section_size:2*section_size]), np.min(lows[2*section_size:])]
        
        if section_lows[1] < section_lows[0] and section_lows[1] < section_lows[2]:
            if abs(section_lows[0] - section_lows[2]) < 0.005 * abs(section_lows[1]):
                neckline = max(section_lows[0], section_lows[2])
                
                if closes[-1] > neckline:
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
    return run_backtest(df, calc_pattern_hns_top, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
