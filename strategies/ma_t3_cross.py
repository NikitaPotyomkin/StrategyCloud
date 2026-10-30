"""MA: T3 Crossover (H1).

Idea: 0244 ma_t3_cross
Вход: T3(8) crosses T3(21)
Выход: reverse cross
Отличие: T3 EMA with smoothness factor
"""
import numpy as np
import pandas as pd


def calc_ma_t3_cross(df, period=8):
    k = 0.7
    
    def t3(series, period, k):
        ema1 = series.ewm(span=period).mean()
        ema2 = ema1.ewm(span=period).mean()
        ema3 = ema2.ewm(span=period).mean()
        ema4 = ema3.ewm(span=period).mean()
        ema5 = ema4.ewm(span=period).mean()
        ema6 = ema5.ewm(span=period).mean()
        
        a = ema6 - ema5
        b = k * a
        return ema6 + b
    
    t3_fast = t3(df['close'], period, k)
    t3_slow = t3(df['close'], period * 2 + 5, k)
    
    k_signal = np.zeros(len(df))
    k_signal[t3_fast > t3_slow] = 1
    k_signal[t3_fast < t3_slow] = -1
    
    df = df.copy()
    df['k'] = k_signal
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
    df = calc_ma_t3_cross(df, int(param_key))
    
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
