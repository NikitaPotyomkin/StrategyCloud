"""Volatility Regime: Rogers-Satchell Break (H1).

Idea: 0003 volreg_rs_break
Вход: Rogers-Satchell > p90(120) и пробой high(20)
Выход: trail 2xATR
Отличие: RS-волатильность работает для трендовых рынков лучше чем GC
"""
import numpy as np
import pandas as pd


def calc_volreg_rs_break(df, period=20):
    """Rogers-Satchell volatility breakout."""
    o = np.log(df['open'])
    h = np.log(df['high'])
    l = np.log(df['low'])
    c = np.log(df['close'])
    
    # RS volatility
    rs_vol = (h - o) * (h - c) + (c - o) * (l - o)
    rs_vol = rs_vol.clip(lower=0)  # ensure non-negative
    
    rolling_mean = rs_vol.rolling(120).mean()
    rolling_std = rs_vol.rolling(120).std()
    p90 = rs_vol.rolling(120).quantile(0.90)
    
    high_20 = rs_vol.rolling(20).max()
    
    k = np.zeros(len(df))
    k[(rs_vol > p90) & (rs_vol > high_20)] = 1
    k[(rs_vol < rolling_mean - rolling_std)] = -1
    
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    if prev == 0 and curr == 1:
        return True
    if prev == 0 and curr == -1:
        return True
    return False


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    df = calc_volreg_rs_break(df, int(param_key))
    
    profit = 0
    n_trades = 0
    trade_profits = []
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        
        for sl in sl_points:
            for tp in tp_points:
                sl_pts = sl * spread_points
                tp_pts = tp * spread_points
                
                if prev_k == 0 and curr_k == 1:
                    entry = df['close'].iloc[i]
                    sl_price = entry - sl_pts * point
                    tp_price = entry + tp_pts * point
                    
                    for j in range(i+1, min(i+50, len(df))):
                        if df['low'].iloc[j] <= sl_price:
                            profit += (sl_price - entry) * sim_lot * tick_value
                            n_trades += 1
                            trade_profits.append(sl_price - entry)
                            break
                        elif df['high'].iloc[j] >= tp_price:
                            profit += (tp_price - entry) * sim_lot * tick_value
                            n_trades += 1
                            trade_profits.append(tp_price - entry)
                            break
                            
                elif prev_k == 0 and curr_k == -1:
                    entry = df['close'].iloc[i]
                    sl_price = entry + sl_pts * point
                    tp_price = entry - tp_pts * point
                    
                    for j in range(i+1, min(i+50, len(df))):
                        if df['high'].iloc[j] >= sl_price:
                            profit += (entry - sl_price) * sim_lot * tick_value
                            n_trades += 1
                            trade_profits.append(entry - sl_price)
                            break
                        elif df['low'].iloc[j] <= tp_price:
                            profit += (entry - tp_price) * sim_lot * tick_value
                            n_trades += 1
                            trade_profits.append(entry - tp_price)
                            break
    
    return (profit, n_trades, trade_profits)
