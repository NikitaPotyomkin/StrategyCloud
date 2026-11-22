"""Strategy: chan_ma_high_low_band (H1).

Idea: Close > max(MA(high),30) — MA high/low band.
Вход: breakout band → signal.
Выход: close < min(MA(low),30).
Отличие: MA high/low band channel.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_chan_ma_high_low_band(df, period=20):
    """MA high/low band breakout.
    
    Breakout of MA(high)/MA(low) band → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # MA bands
        ma_high = np.mean(highs)
        ma_low = np.mean(lows)
        
        # Breakout
        if closes[-1] > ma_high:
            k[i] = 1
        elif closes[-1] < ma_low:
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
    return run_backtest(df, calc_chan_ma_high_low_band, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
