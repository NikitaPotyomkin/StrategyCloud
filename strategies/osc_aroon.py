"""Oscillator: Aroon (H1).

Idea: 0350 osc_aroon_osc
Вход: Aroon Oscillator > 50
Выход: < 0
Отличие: Trend vs reversal detection
"""
import numpy as np
import pandas as pd


def calc_osc_aroon(df, period=25):
    high_25 = df['high'].rolling(period).max()
    low_25 = df['low'].rolling(period).min()
    
    periods_since_high = period - df['high'].rolling(period).apply(lambda x: len(x)-1-x[x==x.max()].index[0], raw=True)
    periods_since_low = period - df['low'].rolling(period).apply(lambda x: len(x)-1-x[x==x.min()].index[0], raw=True)
    
    aroon_up = periods_since_high / period * 100
    aroon_down = periods_since_low / period * 100
    osc = aroon_up - aroon_down
    
    k = np.zeros(len(df))
    k[osc > 50] = 1
    k[osc < 0] = -1
    
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
    df = calc_osc_aroon(df, int(param_key))
    
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
