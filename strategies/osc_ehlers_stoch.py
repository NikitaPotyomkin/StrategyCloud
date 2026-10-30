"""Oscillator: Ehlers Stochastic (H1).

Idea: 0328 osc_ehlers_stoch
Вход: Ehlers Stochastic < 0.2
Выход: > 0.8
Отличие: Ehlers smoothing for stochastic
"""
import numpy as np
import pandas as pd


def calc_osc_ehlers_stoch(df, period=10):
    close_norm = (df['close'] - df['low'].rolling(period).min()) / (df['high'].rolling(period).max() - df['low'].rolling(period).min()).replace(0, np.nan)
    close_norm = close_norm.clip(0, 1)
    
    # Ehlers super smoother
    a1 = np.exp(-1.414 * np.pi / period)
    b1 = 2 * a1 * np.cos(1.414 * np.pi / period)
    c2 = b1
    c3 = -a1 * a1
    c1 = 1 - c2 - c3
    
    smoothed = pd.Series(0, index=df.index)
    for i in range(period, len(df)):
        smoothed.iloc[i] = c1 * close_norm.iloc[i] + c2 * smoothed.iloc[i-1] + c3 * smoothed.iloc[i-2]
    
    k = np.zeros(len(df))
    k[smoothed < 0.2] = 1
    k[smoothed > 0.8] = -1
    
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
    df = calc_osc_ehlers_stoch(df, int(param_key))
    
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
