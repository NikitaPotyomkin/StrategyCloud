"""Mean reversion на основе RSI и скользящей средней (идея ~0247).

Гипотеза: RSI < 20 в сочетании с отклонением цены от SMA(50) > 2σ
даёт сильный сигнал возврата к среднему.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_rsi_sma_z(df, rsi_period=14, sma_period=50, std_mult=2.0):
    """RSI + z-score цены от SMA.
    
    returns: df с колонкой 'k' (комбинированный сигнал)
    """
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(rsi_period).mean()
    avg_loss = loss.rolling(rsi_period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # z-score цены от SMA
    sma = df['close'].rolling(sma_period).mean()
    std = df['close'].rolling(sma_period).std()
    z = (df['close'] - sma) / std
    
    # Комбинация: сильный сигнал когда RSI < 20 и z < -2
    k = (rsi / 100.0) + z
    
    df['k'] = k.values
    return df


def check_entry(prev, curr):
    """Вход при экстремуме (curr < -1.0 и RSI начинает расти)."""
    return prev < -1.0 and curr > prev


def check_exit(prev, curr, direction):
    """Выход при возврате к норме (curr > 0)."""
    return curr > 0.0


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест mean reversion RSI+SMA."""
    parts = str(param_key).split(',') if param_key else '14,50,2.0'
    parts = parts.split('/')
    rsi_period = int(parts[0]) if len(parts) > 0 else 14
    sma_period = int(parts[1]) if len(parts) > 1 else 50
    std_mult = float(parts[2]) if len(parts) > 2 else 2.0
    
    df = calc_rsi_sma_z(df, rsi_period, sma_period, std_mult)
    
    min_len = sma_period + 10
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
        close = df['close'].iloc[i]
        
        # Бинарный сигнал k: 0 если k <= 0, 1 если k > 0
        prev_k_bin = 0 if prev_k <= 0 else 1
        curr_k_bin = 0 if curr_k <= 0 else 1
        
        if not in_pos:
            if prev_k_bin == 0 and curr_k_bin == 1 and check_entry(prev_k, curr_k):
                entry_price = close
                in_pos = True
        else:
            # Проверяем SL/TP по high/low бара
            if low - entry_price <= -sl_dist:
                profit = -sl_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif high - entry_price >= tp_dist:
                profit = tp_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif check_exit(prev_k, curr_k, 'long'):
                profit = (close - entry_price) * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
    
    total_profit = sum(trades)
    return total_profit, len(trades), trades
