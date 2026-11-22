"""Strategy: anom_spike_volume (H1).

Idea: Volume spike > 3× SMA — аномальный объём.
Вход: volume spike → signal.
Выход: 4 бара.
Отличие: volume anomaly detection.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_anom_spike_volume(df, period=20):
    """Volume spike anomaly detection.
    
    Volume > 3× SMA → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        volumes = df['volume'].iloc[i-period:i].values
        
        # Volume SMA
        vol_sma = np.mean(volumes)
        
        # Spike detection
        if volumes[-1] > 3 * vol_sma:
            # Signal in price direction
            if df['close'].iloc[i] > df['open'].iloc[i]:
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
    return run_backtest(df, calc_anom_spike_volume, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
