"""Oscillator: Balance of Power (H1).

Idea: 0347 osc_bop
Вход: BOP > 0 and rising 3 bars
Выход: < 0
Отличие: Balance of power oscillator
"""
import numpy as np
import pandas as pd


def calc_osc_bop(df, period=14):
    hl = df['high'] - df['low']
    bop = (df['close'] - df['open']) / hl.replace(0, np.nan)
    bop_ema = bop.ewm(span=period).mean()
    
    k = np.zeros(len(df))
    k[(bop_ema > 0) & (bop_ema > bop_ema.shift(1)) & (bop_ema > bop_ema.shift(2))] = 1
    k[(bop_ema < 0) & (bop_ema < bop_ema.shift(1)) & (bop_ema < bop_ema.shift(2))] = -1
    
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
    df = calc_osc_bop(df, int(param_key))
    
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
