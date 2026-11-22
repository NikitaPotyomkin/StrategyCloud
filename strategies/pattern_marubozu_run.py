"""Strategy: pattern_marubozu_run (H1).

Idea: 2 marubozu подряд (тело > 90% диапазона) — marubozu run.
Вход: 2 marubozu → signal.
Выход: 3×ATR.
Отличие: marubozu momentum confirmation.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pattern_marubozu_run(df, period=20):
    """Marubozu run detection.
    
    2 consecutive marubozu → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        opens = df['open'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # Marubozu: body > 90% of range
        def is_marubozo(o, c, h, l):
            body = abs(c - o)
            range_ = h - l
            return body > 0.9 * range_ if range_ > 0 else False
        
        # Check last 2 bars
        if is_marubozo(opens[-2], closes[-2], highs[-2], lows[-2]) and \
           is_marubozo(opens[-1], closes[-1], highs[-1], lows[-1]):
            if closes[-1] > opens[-1]:
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
    return run_backtest(df, calc_pattern_marubozu_run, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
