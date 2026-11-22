"""Strategy: mi_adx_rsi_ma (H1).

Idea: ADX + RSI + MA multi-indicator — мультииндикатор.
Вход: ADX>20 + RSI>50 + MA uptrend → long.
Выход: ADX<20.
Отличие: multi-indicator confirmation.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_mi_adx_rsi_ma(df, period=20):
    """Multi-indicator: ADX + RSI + MA.
    
    ADX>20 + RSI>50 + MA uptrend → long.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # ADX proxy
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_mean = atr.rolling(14).mean().iloc[i]
        dx = abs(closes[-1] - closes[-2]) / atr_mean if atr_mean > 0 else 0
        adx = dx * 100
        
        # RSI proxy
        gains = np.maximum(np.diff(closes), 0)
        losses = np.maximum(-np.diff(closes), 0)
        rs = np.mean(gains) / np.mean(losses) if np.mean(losses) > 0 else 10
        rsi = 100 - 100 / (1 + rs)
        
        # MA
        ma = np.mean(closes)
        
        # Multi-indicator signal
        if adx > 20 and rsi > 50 and closes[-1] > ma:
            k[i] = 1
        elif adx > 20 and rsi < 50 and closes[-1] < ma:
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
    return run_backtest(df, calc_mi_adx_rsi_ma, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
