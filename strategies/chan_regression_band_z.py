"""Channel: Regression Band Z (H1).

Idea: 0209 chan_regression_band_z
Вход: regression residual z > 2 and slope > 0
Выход: z < 0
Отличие: Linear regression channel breakout
"""
import numpy as np
import pandas as pd


def calc_chan_regression_band_z(df, period=100):
    x = np.arange(len(df))
    x_rolling = pd.Series(x, index=df.index)
    
    residuals = pd.Series(np.nan, index=df.index)
    slopes = pd.Series(np.nan, index=df.index)
    
    for i in range(period, len(df)):
        y = df['close'].iloc[i-period:i]
        x_i = x_rolling.iloc[i-period:i].values
        try:
            slope, intercept = np.polyfit(x_i, y.values, 1)
            predicted = slope * x_i + intercept
            res = y.values - predicted
            residuals.iloc[i] = res[-1]
            slopes.iloc[i] = slope
        except:
            continue
    
    res_mean = residuals.rolling(50).mean()
    res_std = residuals.rolling(50).std()
    z = (residuals - res_mean) / res_std.replace(0, np.nan)
    
    k = np.zeros(len(df))
    k[(z > 2) & (slopes > 0)] = 1
    k[(z < -2) & (slopes < 0)] = -1
    
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
    df = calc_chan_regression_band_z(df, int(param_key))
    
    profit = 0
    n_trades = 0
    trade_profits = []
    
    sl = sl_points[0]
    tp = tp_points[0]
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        
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
