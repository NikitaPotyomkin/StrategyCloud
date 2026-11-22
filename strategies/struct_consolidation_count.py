"""Strategy: struct_consolidation_count (H1).

Idea: Консолидация — 5+ баров с диапазоном < 0.5×ATR.
Вход: пробой консолидации → сигнал в направлении пробоя.
Выход: trail 1.5×ATR.
Отличие: консолидация перед движением — энергия сжатия.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_consolidation_count(df, period=20):
    """Consolidation detection and breakout.
    
    Detects 5+ consecutive bars with range < 0.5×ATR.
    Breakout from consolidation → signal in breakout direction.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Calculate ATR
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_mean = atr.rolling(20).mean().iloc[i]
        
        # Count consecutive consolidation bars
        cons_count = 0
        for j in range(len(highs)):
            bar_range = highs[j] - lows[j]
            if bar_range < 0.5 * atr_mean:
                cons_count += 1
            else:
                cons_count = 0
        
        # Check for breakout
        if cons_count >= 4:  # 5+ bars including current
            # Bullish breakout
            if closes[-1] > max(highs[:-1]):
                k[i] = 1
            # Bearish breakout
            elif closes[-1] < min(lows[:-1]):
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
    return run_backtest(df, calc_struct_consolidation_count, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
