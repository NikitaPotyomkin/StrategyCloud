"""Strategy: sess_first_hour_bias (H1).

Idea: First hour direction determines day — с первым часом дня.
Вход: первый час дня в направлении EMA200 + ADX>20 → сигнал.
Выход: конец дня.
Отличие: first hour bias — сильный intraday предиктор.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_sess_first_hour_bias(df, period=20):
    """First hour bias strategy.
    
    First hour direction determines day trend with ADX filter.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        opens = df['open'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # First hour range
        first_hour_high = np.max(highs[:1])
        first_hour_low = np.min(lows[:1])
        first_hour_close = closes[0]
        
        # EMA200 trend
        ema200 = df['close'].ewm(span=200, adjust=False).mean().iloc[i]
        
        # ADX filter (simplified)
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_mean = atr.rolling(14).mean().iloc[i]
        trend_strength = abs(closes[-1] - opens[-1]) / atr_mean if atr_mean > 0 else 0
        
        # First hour bias with trend
        if first_hour_close > opens[0] and closes[-1] > ema200 and trend_strength > 0.5:
            k[i] = 1
        elif first_hour_close < opens[0] and closes[-1] < ema200 and trend_strength > 0.5:
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
    return run_backtest(df, calc_sess_first_hour_bias, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
