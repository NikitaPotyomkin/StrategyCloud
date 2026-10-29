"""Mean reversion к средней линии Bollinger Bands (идея ~0245).

Гипотеза: после сильного отклонения от средней BB цена возвращается к ней.
Вход на экстремуме (z > 2.5), выход на касании средней.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_bb_middle_z(df, period=40, std_mult=2.5):
    """Расстояние от цены до средней BB в единицах σ.
    
    returns: df с колонкой 'k' (z от средней BB)
    """
    sma = df['close'].rolling(period).mean()
    std = df['close'].rolling(period).std()
    
    # k = (close - middle) / std — отклонение от средней в σ
    k = (df['close'] - sma) / std
    
    df['k'] = k.values
    return df


def check_entry(prev, curr):
    """Вход при сильном отклонении вниз (curr < -2.5 и начинает расти)."""
    return prev < -2.5 and curr > prev


def check_exit(prev, curr, direction):
    """Выход при возврате к средней (curr > -0.5)."""
    return curr > -0.5


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест mean reversion к средней BB."""
    period = int(param_key) if param_key else 40
    df = calc_bb_middle_z(df, period)
    
    min_len = period + 10
    if len(df) < min_len:
        return 0, 0, []
    
    trades = []
    in_pos = False
    entry_price = 0.0
    
    sl_dist = sl_points * spread_points if spread_points > 0 else sl_points * point
    tp_dist = tp_points * spread_points if spread_points > 0 else tp_points * point
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        close = df['close'].iloc[i]
        
        if not in_pos:
            if check_entry(prev_k, curr_k):
                entry_price = close
                in_pos = True
        else:
            if close - entry_price <= -sl_dist:
                profit = -sl_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif close - entry_price >= tp_dist:
                profit = tp_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif check_exit(prev_k, curr_k, 'long'):
                profit = (close - entry_price) * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
    
    total_profit = sum(trades)
    return total_profit, len(trades), trades
