"""MA: Multi-Cross Vote (H1).

Idea: 0270 ma_multi_cross_vote
Вход: 3 of 5 MA crosses agreed
Выход: 3 against
Отличие: Ensemble of 5 MAs with voting
"""
import numpy as np
import pandas as pd


def calc_ma_multi_cross_vote(df, period=5):
    ma5 = df['close'].rolling(period).mean()
    ma10 = df['close'].rolling(period*2).mean()
    ma20 = df['close'].rolling(period*4).mean()
    ma50 = df['close'].rolling(period*10).mean()
    ma100 = df['close'].rolling(period*20).mean()
    
    votes = 0
    if df['close'] > ma5: votes += 1
    if df['close'] > ma10: votes += 1
    if df['close'] > ma20: votes += 1
    if df['close'] > ma50: votes += 1
    if df['close'] > ma100: votes += 1
    
    k = np.zeros(len(df))
    k[votes >= 3] = 1
    k[votes <= 2] = -1
    
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
    df = calc_ma_multi_cross_vote(df, int(param_key))
    
    profit = 0
    n_trades = 0
    trade_profits = []
    
    sl = sl_points[0]
    tp = tp_points[0]
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        
        sl_price = df['close'].iloc[i] - sl * point
        tp_price = df['close'].iloc[i] + tp * point
        
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
            sl_price = df['close'].iloc[i] + sl * point
            tp_price = df['close'].iloc[i] - tp * point
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
