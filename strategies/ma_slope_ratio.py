"""MA: Slope Ratio (H1).

Idea: 0268 ma_slope_ratio
Вход: slope MA(10)/slope MA(50) > 1.5
Выход: < 0.8
Отличие: Relative slope comparison of two MAs
"""
import numpy as np
import pandas as pd


def calc_ma_slope_ratio(df, period=10):
    ma10 = df['close'].rolling(period).mean()
    ma50 = df['close'].rolling(period * 5).mean()
    
    slope10 = ma10.diff(period)
    slope50 = ma50.diff(period * 5)
    
    ratio = slope10 / slope50.replace(0, np.nan)
    
    k = np.zeros(len(df))
    k[ratio > 1.5] = 1
    k[ratio < 0.8] = -1
    
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
    df = calc_ma_slope_ratio(df, int(param_key))
    
    profit = 0
    n_trades = 0
    trade_profits = []
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        
        for sl in sl_points:
            for tp in tp_points:
                sl_price = df['close'].iloc[i] - sl * spread_points * point
                tp_price = df['close'].iloc[i] + tp * spread_points * point
                
                if prev_k == 0 and curr_k == 1:
                    for j in range(i+1, min(i+50, len(df))):
                        if df['low'].iloc[j] <= sl_price:
                            profit += (sl_price - df['close'].iloc[i]) * sim_lot * tick_value
                            n_trades += 1
                            trade_profits.append(sl_price - df['close'].iloc[i])
                            break
                        elif df['high'].iloc[j] >= tp_price:
                            profit += (tp_price - df['close'].iloc[i]) * sim_lot * tick_value
                            n_trades += 1
                            trade_profits.append(tp_price - df['close'].iloc[i])
                            break
                            
                elif prev_k == 0 and curr_k == -1:
                    sl_price = df['close'].iloc[i] + sl * spread_points * point
                    tp_price = df['close'].iloc[i] - tp * spread_points * point
                    for j in range(i+1, min(i+50, len(df))):
                        if df['high'].iloc[j] >= sl_price:
                            profit += (df['close'].iloc[i] - sl_price) * sim_lot * tick_value
                            n_trades += 1
                            trade_profits.append(df['close'].iloc[i] - sl_price)
                            break
                        elif df['low'].iloc[j] <= tp_price:
                            profit += (df['close'].iloc[i] - tp_price) * sim_lot * tick_value
                            n_trades += 1
                            trade_profits.append(df['close'].iloc[i] - tp_price)
                            break
    
    return (profit, n_trades, trade_profits)
