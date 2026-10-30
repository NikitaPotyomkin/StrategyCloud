"""Breakout continuation на сжатии Keltner (идея ~0208).

Гипотеза: после длительного сжатия канала Keltner (ширина < p15)
следует сильный пробой и продолжение тренда.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_keltner_squeeze(df, period=20, atr_mult=2.0, squeeze_pct=15):
    """Ширина канала Keltner в перцентилях.
    
    returns: df с колонкой 'k' (текущая ширина в % от истории)
    """
    ema = df['close'].ewm(span=period, adjust=False).mean()
    atr = df['high'].rolling(period).mean() - df['low'].rolling(period).mean()
    atr = atr.replace(0, 1e-8)
    
    upper = ema + atr_mult * atr
    lower = ema - atr_mult * atr
    width = upper - lower
    
    # Ширина в перцентилях
    width_pct = width.rolling(period * 12).rank(pct=True)
    
    # Нормализованная ширина (0-1)
    k = width / width.rolling(period * 12).max().replace(0, 1e-8)
    
    df['k'] = k.values
    return df


def check_entry(prev, curr):
    """Вход при выходе из сжатия (curr > 0.7 и растёт)."""
    return prev < 0.5 and curr > 0.7


def check_exit(prev, curr, direction):
    """Выход при снижении ширины (curr < 0.3)."""
    return curr < 0.3


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест breakout continuation на сжатии Keltner."""
    period = int(param_key) if param_key else 20
    df = calc_keltner_squeeze(df, period)
    
    min_len = period * 12 + 20
    if len(df) < min_len:
        return 0, 0, []
    
    trades = []
    in_pos = False
    entry_price = 0.0
    
    sl_dist = sl_points * point
    tp_dist = tp_points * point

    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        close = df['close'].iloc[i]
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]

        if not in_pos:
            if prev_k < 0.5 and curr_k > 0.7:
                entry_price = close
                in_pos = True
        else:
            if low <= entry_price - sl_dist:
                profit = -sl_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif high >= entry_price + tp_dist:
                profit = tp_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif check_exit(prev_k, curr_k, 'long'):
                profit = (close - entry_price) * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
    
    total_profit = sum(trades)
    return total_profit, len(trades), trades
