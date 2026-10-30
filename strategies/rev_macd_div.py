"""Reversal на дивергенции MACD (идея ~0250).

Гипотеза: дивергенция между MACD и ценой — сильный сигнал разворота.
Цена делает новый экстремум, MACD нет.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_macd_divergence(df, fast=12, slow=26, signal=9):
    """Дивергенция MACD-цена.
    
    returns: df с колонкой 'k' (сигнал дивергенции)
    """
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    # Поиск экстремумов цены
    high_peak = df['high'].rolling(10).max().shift(10)
    low_trough = df['low'].rolling(10).min().shift(10)
    
    # Новый high + histogram не выше прошлого
    bearish_div = (df['high'] > high_peak) & (histogram > histogram.shift(10))
    
    # Новый low + histogram не ниже прошлого
    bullish_div = (df['low'] < low_trough) & (histogram < histogram.shift(10))
    
    # Сила сигнала
    range_val = df['high'] - df['low']
    
    k = np.where(
        bearish_div,
        -histogram / range_val.replace(0, 1e-8),
        np.where(
            bullish_div,
            histogram / range_val.replace(0, 1e-8),
            0.0
        )
    )
    
    df['k'] = k
    
    return df


def check_entry(prev, curr):
    """Вход при дивергенции (|curr| > 0.3)."""
    return prev < 0.3 and abs(curr) > 0.3


def check_exit(prev, curr, direction):
    """Выход при затухании."""
    return abs(curr) < 0.1


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест reversal на дивергенции MACD."""
    parts = str(param_key).split(',') if param_key else '12,26,9'
    fast = int(parts[0]) if len(parts) > 0 else 12
    slow = int(parts[1]) if len(parts) > 1 else 26
    signal = int(parts[2]) if len(parts) > 2 else 9
    
    df = calc_macd_divergence(df, fast, slow, signal)
    
    min_len = 40
    if len(df) < min_len:
        return 0, 0, []
    
    trades = []
    in_pos = False
    entry_price = 0.0
    
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    position_dir = 0  # 1 = long, -1 = short

    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        close = df['close'].iloc[i]
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]

        if not in_pos:
            if prev_k == 0 and curr_k != 0:
                entry_price = close
                in_pos = True
                position_dir = 1 if curr_k > 0 else -1
        else:
            if position_dir == 1:
                # Long: SL по low, TP по high
                if low <= entry_price - sl_dist:
                    profit = -sl_dist * tick_value * sim_lot
                    trades.append(profit)
                    in_pos = False
                elif high >= entry_price + tp_dist:
                    profit = tp_dist * tick_value * sim_lot
                    trades.append(profit)
                    in_pos = False
            else:
                # Short: SL по high, TP по low
                if high >= entry_price + sl_dist:
                    profit = -sl_dist * tick_value * sim_lot
                    trades.append(profit)
                    in_pos = False
                elif low <= entry_price - tp_dist:
                    profit = tp_dist * tick_value * sim_lot
                    trades.append(profit)
                    in_pos = False
            if in_pos and check_exit(prev_k, curr_k, 'long'):
                profit = (close - entry_price) * position_dir * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
    
    total_profit = sum(trades)
    return total_profit, len(trades), trades
