"""Strategy: cyc_fft_power_ratio (H1).

Idea: Dominant frequency power share > p70 — доминирующая частота FFT.
Вход: power share > p70 → signal.
Выход: power share < p50.
Отличие: FFT спектральный анализ доминирующей частоты.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_cyc_fft_power_ratio(df, period=20):
    """FFT dominant frequency power ratio.
    
    Dominant frequency power share > p70 → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # FFT
        fft = np.fft.fft(closes - np.mean(closes))
        power = np.abs(fft)**2
        
        # Total power
        total_power = np.sum(power)
        
        if total_power > 0:
            # Dominant frequency power ratio
            dominant_power = np.max(power[1:])  # Skip DC component
            power_ratio = dominant_power / total_power
            
            # Signal on high power ratio
            if power_ratio > 0.7:
                # Direction from dominant frequency phase
                dominant_idx = np.argmax(power[1:]) + 1
                phase = np.angle(fft[dominant_idx])
                
                if np.cos(phase) > 0:
                    k[i] = 1
                else:
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
    return run_backtest(df, calc_cyc_fft_power_ratio, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
