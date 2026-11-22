"""Strategy: ma_alma_trend (H1).

Idea: Close > ALMA(21,0.85,6) — Arnaud Legoux Moving Average.
Вход: цена выше ALMA → long.
Выход: цена ниже ALMA.
Отличие: ALMA — гауссовское сглаживание, меньше lag.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_ma_alma_trend(df, period=20):
    """ALMA (Arnaud Legoux Moving Average) trend.
    
    Price above ALMA → long signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # ALMA parameters
        sigma = 6.0
        offset = 0.85
        
        # ALMA calculation
        m = offset * (period - 1)
        s = period / sigma
        
        weights = np.exp(-((np.arange(period) - m)**2) / (2 * s**2))
        weights /= np.sum(weights)
        
        alma = np.sum(closes * weights)
        
        # Signal
        if closes[-1] > alma:
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
    return run_backtest(df, calc_ma_alma_trend, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
