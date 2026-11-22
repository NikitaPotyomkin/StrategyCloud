"""Strategy: cyc_wavelet_denoise (H1).

Idea: Entry on wavelet-denoised signal — вейвлет сглаживание.
Вход: wavelet-denoised signal → signal.
Выход: opposite.
Отличие: wavelet denoising удаляет шум лучше MA.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_cyc_wavelet_denoise(df, period=20):
    """Wavelet denoising signal.
    
    Entry on wavelet-denoised signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Simple wavelet-like denoising (moving average proxy)
        window = 5
        if len(closes) >= window:
            # Denoised signal (rolling mean)
            denoised = np.mean(closes[-window:])
            
            # Signal direction
            if denoised > closes[-window]:
                k[i] = 1
            elif denoised < closes[-window]:
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
    return run_backtest(df, calc_cyc_wavelet_denoise, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
