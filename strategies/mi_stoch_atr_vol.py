"""Multi-indicator composite: Stochastic + ATR + Volume (идея ~0264).

Гипотеза: стохастик в зоне перепроданности + расширение ATR +
рост объёма = начало сильного движения.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_stoch_atr_vol(df, stoch_period=14, atr_period=14, vol_period=30):
    """Композит: Stochastic + ATR + Volume.
    
    returns: df с колонкой 'k' (score -1..1)
    """
    # Stochastic %K
    low_14 = df['low'].rolling(stoch_period).min()
    high_14 = df['high'].rolling(stoch_period).max()
    range_14 = (high_14 - low_14).replace(0, 1e-8)
    k_fast = 100 * (df['close'] - low_14) / range_14
    
    # ATR
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift()).abs()
    tr3 = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean()
    
    # Volume z-score
    vol_mean = df['volume'].rolling(vol_period).mean()
    vol_std = df['volume'].rolling(vol_period).std()
    vol_z = (df['volume'] - vol_mean) / vol_std.replace(0, 1e-8)
    
    # Композит: %K < 20 + vol_z > 0.5 → сигнал вверх
    # %K > 80 + vol_z > 0.5 → сигнал вниз
    stoch_signal = np.where(k_fast < 20, 1.0, np.where(k_fast > 80, -1.0, 0.0))
    vol_conf = np.where(vol_z > 0.5, 1.0, 0.5)
    
    k = stoch_signal * vol_conf
    
    df['k'] = k.values
    
    return df


def check_entry(prev, curr):
    """Вход при сильном сигнале (|curr| > 0.7)."""
    return prev < 0.7 and abs(curr) > 0.7


def check_exit(prev, curr, direction):
    """Выход при ослаблении."""
    return abs(curr) < 0.4


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест multi-indicator Stochastic+ATR+Volume."""
    parts = str(param_key).split(',') if param_key else '14,14,30'
    stoch_period = int(parts[0]) if len(parts) > 0 else 14
    atr_period = int(parts[1]) if len(parts) > 1 else 14
    vol_period = int(parts[2]) if len(parts) > 2 else 30
    
    df = calc_stoch_atr_vol(df, stoch_period, atr_period, vol_period)
    
    min_len = max(stoch_period, atr_period, vol_period) + 10
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
