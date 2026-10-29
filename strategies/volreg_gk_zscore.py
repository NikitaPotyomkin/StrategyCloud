"""Volatility Regime: Garman-Klass Z-Score (H1).

Idea: 0002 volreg_gk_zscore
Вход: Garman-Klass z > 2
Выход: VWAP дня или 8 баров
Отличие: GK-волатильность (open/close/high/low), более точная чем ATR
"""
import numpy as np
import pandas as pd


def calc_volreg_gk_zscore(df, period=20):
    """Расчёт Garman-Klass volatility z-score."""
    # GK volatility estimator
    a = np.log(df['high'] / df['low']) ** 2
    b = np.log(df['close'] / df['open']) ** 2
    gk_vol = 0.5 * a - (2.0 * np.log(2) - 1) * b
    
    rolling_mean = gk_vol.rolling(period).mean()
    rolling_std = gk_vol.rolling(period).std()
    z = (gk_vol - rolling_mean) / rolling_std.replace(0, np.nan)
    
    k = np.zeros(len(df))
    k[z > 2.0] = 1
    k[z < -2.0] = -1
    
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    if prev == 0 and curr == 1:
        return True
    if prev == 0 and curr == -1:
        return True
    return False


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    df = calc_volreg_gk_zscore(df, int(param_key))
    
    profit = 0
    n_trades = 0
    trade_profits = []
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        
        for sl in sl_points:
            for tp in tp_points:
                sl_pts = sl * spread_points
                tp_pts = tp * spread_points
                
                if prev_k == 0 and curr_k == 1:
                    entry = df['close'].iloc[i]
                    sl_price = entry - sl_pts * point
                    tp_price = entry + tp_pts * point
                    
                    pnl = 0
                    for j in range(i+1, min(i+50, len(df))):
                        high = df['high'].iloc[j]
                        low = df['low'].iloc[j]
                        if low <= sl_price:
                            pnl = (sl_price - entry) * sim_lot * tick_value
                            break
                        elif high >= tp_price:
                            pnl = (tp_price - entry) * sim_lot * tick_value
                            break
                    profit += pnl
                    n_trades += 1
                    trade_profits.append(pnl)
                    
                elif prev_k == 0 and curr_k == -1:
                    entry = df['close'].iloc[i]
                    sl_price = entry + sl_pts * point
                    tp_price = entry - tp_pts * point
                    
                    pnl = 0
                    for j in range(i+1, min(i+50, len(df))):
                        high = df['high'].iloc[j]
                        low = df['low'].iloc[j]
                        if high >= sl_price:
                            pnl = (entry - sl_price) * sim_lot * tick_value
                            break
                        elif low <= tp_price:
                            pnl = (entry - tp_price) * sim_lot * tick_value
                            break
                    profit += pnl
                    n_trades += 1
                    trade_profits.append(pnl)
    
    return (profit, n_trades, trade_profits)
