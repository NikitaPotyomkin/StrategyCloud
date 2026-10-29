"""Advanced stat: Fractal Dimension regime (идея ~0292).

Гипотеза: фрактальная размерность Холла измеряет "сглаженность" тренда:
FD < 0.7 — сильный тренд (следовать)
FD > 1.3 — шум (не торговать)
0.7 < FD < 1.0 — слабый тренд (осторожно)

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_fractal_dimension(df, period=20):
    """Фрактальная размерность Холла (Hurst-based).
    
    FD = 2 - H
    
    returns: df с колонкой 'k' (fractal dimension)
    """
    returns = df['close'].pct_change().dropna()
    
    fd_vals = []
    
    for i in range(len(returns)):
        if i < period:
            fd_vals.append(1.0)
            continue
        
        window = returns.iloc[i - period:i].values
        
        # Mean and standard deviation
        mean_ret = np.mean(window)
        std_ret = np.std(window)
        
        if std_ret < 1e-8:
            fd_vals.append(1.0)
            continue
        
        # Log return variance
        log_var = np.log(std_ret ** 2 + 1e-16)
        
        # H approximation через scaling
        # Используем simple R/S approach
        cum_dev = np.cumsum(window - mean_ret)
        r = np.max(cum_dev) - np.min(cum_dev)
        s = std_ret * np.sqrt(period)
        
        if s < 1e-8 or r < 1e-8:
            fd_vals.append(1.0)
            continue
        
        rs_ratio = r / s
        h = np.log(rs_ratio + 1e-16) / np.log(np.sqrt(period) + 1e-16)
        h = np.clip(h, 0.0, 1.0)
        
        # FD = 2 - H
        fd = 2.0 - h
        
        fd_vals.append(fd)
    
    df['k'] = np.array(fd_vals)
    
    return df


def check_entry(prev, curr):
    """Вход при сильном тренде (curr < 0.8)."""
    return prev > 0.8 and curr < 0.8


def check_exit(prev, curr, direction):
    """Выход при росте шума (curr > 1.3)."""
    return curr > 1.3


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест на fractal dimension."""
    period = int(param_key) if param_key else 20
    df = calc_fractal_dimension(df, period)
    
    min_len = period + 10
    if len(df) < min_len:
        return 0, 0, []
    
    trades = []
    in_pos = False
    entry_price = 0.0
    
    sl_dist = sl_points * spread_points if spread_points > 0 else sl_points * point
    tp_dist = tp_points * spread_points if spread_points > 0 else tp_points * point
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        close = df['close'].iloc[i]
        
        if not in_pos:
            if check_entry(prev_k, curr_k):
                entry_price = close
                in_pos = True
        else:
            if close - entry_price <= -sl_dist:
                profit = -sl_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif close - entry_price >= tp_dist:
                profit = tp_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif check_exit(prev_k, curr_k, 'long'):
                profit = (close - entry_price) * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
    
    total_profit = sum(trades)
    return total_profit, len(trades), trades
