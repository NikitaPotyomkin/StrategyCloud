"""Statistical: Lempel-Ziv Complexity (H1).

Idea: 0514 stat_lz_complexity
Вход: Lempel-Ziv complexity of ret-string falls
Выход: rises
Отличие: Information-theoretic complexity measure
"""
import numpy as np
import pandas as pd


def calc_stat_lz_complexity(df, period=200):
    ret = df['close'].pct_change()
    binary = (ret > 0).astype(int).astype(str)
    s = ''.join(binary.iloc[period:])
    
    complexity = pd.Series(np.nan, index=df.index)
    
    for i in range(period, len(df)):
        sub_s = s[:i-period+1]
        count = 0
        start = 0
        while start < len(sub_s):
            found = False
            for end in range(start+1, len(sub_s)+1):
                if sub_s[start:end] not in sub_s[start:start+end-start]:
                    continue
                if sub_s[start:end] in sub_s[:start]:
                    start = end
                    found = True
                    break
            if not found:
                start += 1
        complexity.iloc[i] = count
    
    c_mean = complexity.rolling(50).mean()
    c_std = complexity.rolling(50).std()
    z = (complexity - c_mean) / c_std.replace(0, np.nan)
    
    k = np.zeros(len(df))
    k[z < -2] = 1  # low complexity = trend
    k[z > 2] = -1  # high complexity = noise
    
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
    df = calc_stat_lz_complexity(df, int(param_key))
    
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
