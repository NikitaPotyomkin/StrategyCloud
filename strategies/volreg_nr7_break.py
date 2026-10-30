"""Volatility: NR7 Breakout (H1).

Idea: 0019 volreg_nr7_break
Вход: NR7 (narrowest bar in 7) + breakout
Выход: trail 2xATR
Отличие: Narrow Range 7 pattern
"""
import numpy as np
import pandas as pd


def calc_volreg_nr7_break(df, n=7):
    tr = np.maximum(df['high'] - df['low'], np.abs(df['high'] - df['close'].shift(1)))
    range_7 = tr.rolling(n).min()
    is_nr7 = tr == range_7
    
    high_7 = df['high'].rolling(n).max()
    low_7 = df['low'].rolling(n).min()
    
    k = np.zeros(len(df))
    k[(is_nr7) & (df['close'] > high_7.shift(1))] = 1
    k[(is_nr7) & (df['close'] < low_7.shift(1))] = -1
    
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    return (prev == 0 and curr == 1) or (prev == 0 and curr == -1)


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    df = calc_volreg_nr7_break(df, int(param_key))
    
    profit = 0
    n_trades = 0
    trade_profits = []
    
    # SL/TP в пунктах (не в спредах)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        
        if prev_k == 0 and curr_k == 1:
            entry_price = df['close'].iloc[i]
            sl_price = entry_price - sl_dist
            tp_price = entry_price + tp_dist
            for j in range(i+1, min(i+50, len(df))):
                if df['low'].iloc[j] <= sl_price:
                    profit += (sl_price - entry_price) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(sl_price - entry_price)
                    break
                elif df['high'].iloc[j] >= tp_price:
                    profit += (tp_price - entry_price) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(tp_price - entry_price)
                    break
                        
        elif prev_k == 0 and curr_k == -1:
            entry_price = df['close'].iloc[i]
            sl_price = entry_price + sl_dist
            tp_price = entry_price - tp_dist
            for j in range(i+1, min(i+50, len(df))):
                if df['high'].iloc[j] >= sl_price:
                    profit += (entry_price - sl_price) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(entry_price - sl_price)
                    break
                elif df['low'].iloc[j] <= tp_price:
                    profit += (entry_price - tp_price) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(entry_price - tp_price)
                    break
    
    return (profit, n_trades, trade_profits)
