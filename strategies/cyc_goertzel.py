"""Strategy: cyc_goertzel (H1).

Idea: Specific frequency strength (Goertzel) rising — фильтр Goertzel.
Вход: strength rising → signal.
Выход: strength falling.
Отличие: Goertzel — эффективный детект конкретной частоты.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_cyc_goertzel(df, period=20):
    """Goertzel frequency detection.
    
    Specific frequency strength rising → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Goertzel algorithm for specific frequency
        target_freq = 0.1  # Target frequency
        n = len(closes)
        
        # Goertzel coefficient
        omega = 2 * np.pi * target_freq
        coeff = 2 * np.cos(omega)
        
        # Process
        s_prev = 0
        s_prev2 = 0
        
        for s in closes:
            s_new = coeff * s_prev - s_prev2 + s
            s_prev2 = s_prev
            s_prev = s_new
        
        # Power
        power = s_prev2**2 + s_prev**2 - coeff * s_prev2 * s_prev
        
        # Rising power
        if i > 1:
            prev_closes = df['close'].iloc[i-period-1:i-1].values
            s_prev2_old = 0
            s_prev_old = 0
            
            for s in prev_closes:
                s_new = coeff * s_prev_old - s_prev2_old + s
                s_prev2_old = s_prev_old
                s_prev_old = s_new
            
            power_old = s_prev_old**2 + s_prev2_old**2 - coeff * s_prev_old * s_prev2_old
            
            if power > power_old:
                k[i] = 1
            elif power < power_old:
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
    return run_backtest(df, calc_cyc_goertzel, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
