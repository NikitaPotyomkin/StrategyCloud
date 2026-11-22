"""Strategy: osc_ehlers_stoch (H1).

Idea: Ehlers Stochastic — стохастик Ehlers.
В вход: Ehlers Stoch > threshold → signal.
Выход: threshold cross.
Отличие: Ehlers filter reduces noise.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_osc_ehlers_stoch(df, period=20):
    """Ehlers Stochastic oscillator.
    
    Ehlers Stoch > threshold → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # Ehlers Stochastic proxy
        hh = np.max(highs)
        ll = np.min(lows)
        
        if hh > ll:
            stoch = (closes[-1] - ll) / (hh - ll)
            
            # Signal
            if stoch > 0.8:
                k[i] = -1
            elif stoch < 0.2:
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
    return run_backtest(df, calc_osc_ehlers_stoch, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
