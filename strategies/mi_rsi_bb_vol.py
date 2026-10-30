"""Multi-indicator composite: RSI + BB + Volume (идея ~0260).

Гипотеза: комбинация трёх независимых сигналов (RSI экстремум,
BB пробой, объёмный спайк) даёт высокий PF при редких сигналах.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_rsi_bb_vol(df, rsi_period=14, bb_period=20, bb_std=2.0, vol_period=30):
    """Композитный сигнал: RSI + BB + Volume.
    
    returns: df с колонкой 'k' (композитный score -1..1)
    """
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(rsi_period).mean()
    avg_loss = loss.rolling(rsi_period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # BB
    sma = df['close'].rolling(bb_period).mean()
    std = df['close'].rolling(bb_period).std()
    bb_lower = sma - bb_std * std
    bb_upper = sma + bb_std * std
    
    # %B
    bb_width = (bb_upper - bb_lower).replace(0, 1e-8)
    pct_b = (df['close'] - bb_lower) / bb_width
    
    # Volume z-score
    vol_mean = df['volume'].rolling(vol_period).mean()
    vol_std = df['volume'].rolling(vol_period).std()
    vol_z = (df['volume'] - vol_mean) / vol_std.replace(0, 1e-8)
    
    # Композит: RSI < 30 + %B < 0.1 + vol_z > 1 → сильный сигнал вверх
    # RSI > 70 + %B > 0.9 + vol_z > 1 → сильный сигнал вниз
    rsi_signal = np.where(rsi < 30, 1.0, np.where(rsi > 70, -1.0, 0.0))
    bb_signal = np.where(pct_b < 0.1, 1.0, np.where(pct_b > 0.9, -1.0, 0.0))
    vol_signal = np.where(vol_z > 1.0, 1.0, 0.0)
    
    k = (rsi_signal + bb_signal) * vol_signal / 2.0
    
    df['k'] = k.values
    
    return df


def check_entry(prev, curr):
    """Вход при сильном композитном сигнале (|curr| > 1.0)."""
    return prev < 1.0 and abs(curr) > 1.0


def check_exit(prev, curr, direction):
    """Выход при ослаблении сигнала."""
    return abs(curr) < 0.5


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест multi-indicator composite."""
    parts = str(param_key).split(',') if param_key else '14,20,2.0,30'
    rsi_period = int(parts[0]) if len(parts) > 0 else 14
    bb_period = int(parts[1]) if len(parts) > 1 else 20
    bb_std = float(parts[2]) if len(parts) > 2 else 2.0
    vol_period = int(parts[3]) if len(parts) > 3 else 30
    
    df = calc_rsi_bb_vol(df, rsi_period, bb_period, bb_std, vol_period)
    
    min_len = max(bb_period, vol_period) + 10
    if len(df) < min_len:
        return 0, 0, []
    
    trades = []
    in_pos = False
    entry_price = 0.0
    
    sl_dist = sl_points * point
    tp_dist = tp_points * point

    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]

        if not in_pos:
            if prev_k == 0 and curr_k == 1:
                entry_price = df['close'].iloc[i]
                in_pos = True
        else:
            if low - entry_price <= -sl_dist:
                profit = -sl_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif high - entry_price >= tp_dist:
                profit = tp_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif check_exit(prev_k, curr_k, 'long'):
                profit = (df['close'].iloc[i] - entry_price) * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
    
    total_profit = sum(trades)
    return total_profit, len(trades), trades
