"""Volatility Regime: Yang-Zhang Regime (H1).

Idea: 0004 volreg_yz_regime
Вход: Yang-Zhang(24) grows 3 bars + close > SMA50
Выход: opposite signal
Отличие: YZ-волатильность включает overnight gaps
"""
import numpy as np
import pandas as pd


def calc_volreg_yz_regime(df, period=24):
    """Yang-Zhang volatility regime detection."""
    o = np.log(df['open'])
    h = np.log(df['high'])
    l = np.log(df['low'])
    c = np.log(df['close'])
    
    # Overnight return variance
    overnight = (o - c.shift(1)) ** 2
    # Intraday return variance
    intraday = (h - l) ** 2
    # Close-to-close variance
    close_close = (c - c.shift(1)) ** 2
    
    # YZ decomposition
    n = len(df)
    yz_vol = pd.Series(0.0, index=df.index)
    
    for i in range(period, n):
        overnight_hist = overnight.iloc[i-period+1:i+1]
        intraday_hist = intraday.iloc[i-period+1:i+1]
        close_close_hist = close_close.iloc[i-period+1:i+1]
        
        sigma_overnight = overnight_hist.mean()
        sigma_intraday = intraday_hist.mean()
        sigma_close = close_close_hist.mean()
        
        k = sigma_overnight / (sigma_overnight + sigma_intraday)
        yz = sigma_close + (1.0 / (period - 1)) * sum(
            (sigma_overnight + sigma_intraday - sigma_close) ** 2 
            for j in range(period)
        )
        yz_vol.iloc[i] = yz ** 0.5
    
    sma50 = df['close'].rolling(50).mean()
    growing = (yz_vol > yz_vol.shift(1)) & (yz_vol > yz_vol.shift(2)) & (yz_vol > yz_vol.shift(3))
    
    k = np.zeros(len(df))
    k[(growing) & (df['close'] > sma50)] = 1
    k[(yz_vol < yz_vol.shift(1) * 0.8) & (df['close'] < sma50)] = -1
    
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
    df = calc_volreg_yz_regime(df, int(param_key))
    
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
