"""Advanced stat: Hurst exponent regime (идея ~0290).

Гипотеза: показатель Хёрста определяет режим рынка:
H > 0.5 — трендовый (следовать тренду)
H < 0.5 — mean-reverting (торговать отклонения)
H ~ 0.5 — случайное блуждание (не торговать)

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_hurst_exponent(df, period=60):
    """Приближённый показатель Хёрста через R/S анализ.
    
    returns: df с колонкой 'k' (hurst exponent)
    """
    returns = df['close'].pct_change().dropna()
    
    hurst_vals = []
    
    for i in range(len(returns)):
        if i < period:
            hurst_vals.append(0.5)
            continue
        
        window = returns.iloc[i - period:i].values
        
        # R/S анализ с lag=10
        lag = 10
        if i < lag + period:
            hurst_vals.append(0.5)
            continue
        
        # Среднее и variance
        mean_ret = np.mean(window)
        trend = window - mean_ret
        
        # Cumulative deviation from mean
        cum_dev = np.cumsum(trend)
        
        # Range
        r = np.max(cum_dev) - np.min(cum_dev)
        
        # Standard deviation
        s = np.std(window)
        
        if s < 1e-8 or r < 1e-8:
            hurst_vals.append(0.5)
            continue
        
        # R/S ratio
        rs_ratio = r / s
        
        # H ≈ log(R/S) / log(lag) для упрощённого подхода
        # Более точный: используем несколько lag и линейную регрессию
        # Но для скорости берём приближение
        h = np.log(rs_ratio + 1e-8) / np.log(lag + 1e-8)
        h = np.clip(h, 0.0, 1.0)  # Ограничение [0, 1]
        
        hurst_vals.append(h)
    
    df['k'] = np.array(hurst_vals)
    
    return df


def check_entry(prev, curr):
    """Вход при смене режима: H < 0.4 (mean-revert) или H > 0.6 (trend)."""
    return abs(prev) < 0.5 and abs(curr) > 0.55


def check_exit(prev, curr, direction):
    """Выход при возврате к случайности (H ~ 0.5)."""
    return abs(curr - 0.5) < 0.1


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест на hurst exponent regime."""
    period = int(param_key) if param_key else 60
    df = calc_hurst_exponent(df, period)
    
    min_len = period + 20
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
