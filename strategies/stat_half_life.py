"""Statistical: Half-Life Mean Reversion (H1).

Idea: 0519 stat_half_life
Вход: half-life return < 10 bars → mean-reversion
Выход: > 30
Отличие: Ornstein-Uhlenbeck half-life estimation
"""
import numpy as np
import pandas as pd


def calc_stat_half_life(df, period=200):
    ret = df['close'].pct_change()
    
    half_life = pd.Series(np.nan, index=df.index)
    
    for i in range(period, len(df)):
        y = ret.iloc[i-period:i]
        x = y.shift(1).dropna()
        y = y.iloc[1:].reset_index(drop=True)
        
        if x.empty or y.empty:
            continue
            
        try:
            theta = -(np.cov(x.values, y.values)[0, 1] / np.var(x.values))
            hl = np.log(2) / theta if theta > 0 else np.inf
            half_life.iloc[i] = hl
        except:
            continue
    
    k = np.zeros(len(df))
    k[half_life.notna() & (half_life < 10)] = 1
    k[half_life.notna() & (half_life > 30)] = -1
    
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
    df = calc_stat_half_life(df, int(param_key))
    
    profit = 0
    n_trades = 0
    trade_profits = []
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        
        sl = sl_points[0]
        tp = tp_points[0]

        if prev_k == 0 and curr_k == 1:
            sl_price = df['close'].iloc[i] - sl * point
            tp_price = df['close'].iloc[i] + tp * point
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
