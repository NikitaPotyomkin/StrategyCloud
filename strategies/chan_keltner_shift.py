"""Strategy: chan_keltner_shift (H1).

Idea: Keltner(20,2ATR) со сдвигом средней на 1 бар — сдвинутый Keltner.
Вход: пробой → signal.
Выход: средняя.
Отличие: shifted Keltner reduces lag.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_chan_keltner_shift(df, period=20):
    """Shifted Keltner channel.
    
    Breakout of shifted Keltner → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Shifted Keltner middle (SMA shifted by 1)
        kelt_mid = np.mean(closes[:-1]) if len(closes) > 1 else np.mean(closes)
        
        # ATR
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_mean = atr.rolling(20).mean().iloc[i]
        
        # Keltner bands
        kelt_upper = kelt_mid + 2 * atr_mean
        kelt_lower = kelt_mid - 2 * atr_mean
        
        # Breakout
        if closes[-1] > kelt_upper:
            k[i] = 1
        elif closes[-1] < kelt_lower:
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
    return run_backtest(df, calc_chan_keltner_shift, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
