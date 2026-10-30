"""Regime: Vol Switch (H1).

Idea: 0535 regime_vol_switch
Вход: σ(20)/σ(100) crosses 1 from below
Выход: back below 1
Отличие: Volatility regime change detection
"""
import numpy as np
import pandas as pd


def calc_regime_vol_switch(df, period=20):
    vol_20 = df['close'].pct_change().rolling(20).std()
    vol_100 = df['close'].pct_change().rolling(100).std()
    ratio = vol_20 / vol_100.replace(0, np.nan)
    
    k = np.zeros(len(df))
    k[(ratio > 1) & (ratio.shift(1) <= 1)] = 1
    k[(ratio < 1) & (ratio.shift(1) >= 1)] = -1
    
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
    df = calc_regime_vol_switch(df, int(param_key))

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
