"""Volatility: Choppiness Index (H1).

Idea: 0011 volreg_choppiness
Вход: Choppiness(14) < 38 and close > SMA(100)
Выход: Choppiness > 62
Отличие: Choppiness index for trend detection
"""
import numpy as np
import pandas as pd


def calc_volreg_choppiness(df, period=14):
    tr = np.maximum(df['high'] - df['low'], np.abs(df['high'] - df['close'].shift(1)))
    sum_tr = tr.rolling(period).sum()
    diff_close = df['high'].rolling(period).max() - df['low'].rolling(period).min()
    
    choppiness = 100 * np.log10(sum_tr / diff_close.replace(0, np.nan)) / np.log10(period)
    
    sma_100 = df['close'].rolling(100).mean()
    
    k = np.zeros(len(df))
    k[(choppiness < 38) & (df['close'] > sma_100)] = 1
    k[(choppiness > 62)] = -1
    
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
    df = calc_volreg_choppiness(df, int(param_key))
    
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
            # Long: пробой вверх
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
            # Short: пробой вниз
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
