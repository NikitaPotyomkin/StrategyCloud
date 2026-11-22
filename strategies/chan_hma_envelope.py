"""Strategy: chan_hma_envelope (H1).

Idea: Price выше HMA-envelope (+1 ATR) — Hull MA envelope.
Вход: breakout envelope → signal.
Выход: внутри envelope.
Отличие: HMA reduces lag.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_chan_hma_envelope(df, period=20):
    """HMA envelope breakout.
    
    Breakout of HMA + 1 ATR envelope → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # HMA proxy (weighted MA)
        hma = np.mean(closes[-int(period/2):]) * 2 - np.mean(closes[:int(period/2)])
        
        # ATR
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_mean = atr.rolling(20).mean().iloc[i]
        
        # Envelope
        upper = hma + atr_mean
        lower = hma - atr_mean
        
        # Breakout
        if closes[-1] > upper:
            k[i] = 1
        elif closes[-1] < lower:
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
    return run_backtest(df, calc_chan_hma_envelope, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
