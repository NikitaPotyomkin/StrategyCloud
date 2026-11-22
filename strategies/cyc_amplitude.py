"""Strategy: cyc_amplitude (H1).

Idea: Cycle amplitude rises 3 bars — амплитуда цикла.
Вход: amplitude rises 3 bars → long.
Выход: amplitude falls.
Отличие: detection cycle amplitude change.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_cyc_amplitude(df, period=20):
    """Cycle amplitude detection.
    
    Amplitude rises 3 bars → long.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Amplitude as range
        amplitude = np.max(closes) - np.min(closes)
        
        # Rising amplitude
        if i > 2:
            prev_closes = df['close'].iloc[i-period-1:i-1].values
            prev_amplitude = np.max(prev_closes) - np.min(prev_closes)
            
            if amplitude > prev_amplitude:
                k[i] = 1
            elif amplitude < prev_amplitude:
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
    return run_backtest(df, calc_cyc_amplitude, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
