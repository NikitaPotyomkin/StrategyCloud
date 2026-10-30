"""Reversal на swing failure pivot (идея ~0160).

Гипотеза: неудавшийся пробой свинга (прокол и быстрый возврат)
— сильный сигнал разворота.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_swing_failure(df, lookback=10, tolerance=0.05):
    """Swing failure pivot.
    
    returns: df с колонкой 'k' (сила failure-сигнала)
    """
    high_rolling = df['high'].rolling(lookback).max()
    low_rolling = df['low'].rolling(lookback).min()
    
    # Proкол выше high, закрытие ниже (бычий failure)
    bullish_fail = (df['low'] < low_rolling) & (df['close'] > low_rolling + tolerance * (df['high'] - df['low']))
    
    # Proкол ниже low, закрытие выше (медвежий failure)
    bearish_fail = (df['high'] > high_rolling) & (df['close'] < high_rolling - tolerance * (df['high'] - df['low']))
    
    # Сила: насколько близко закрытие к противоположной стороне
    range_val = df['high'] - df['low']
    
    k = np.where(
        bullish_fail,
        (df['close'] - df['low']) / range_val.replace(0, 1e-8),
        np.where(
            bearish_fail,
            -((df['high'] - df['close']) / range_val.replace(0, 1e-8)),
            0.0
        )
    )
    
    df['k'] = k
    
    return df


def check_entry(prev, curr):
    """Вход при failure-сигнале (|curr| > 0.6)."""
    return prev < 0.6 and abs(curr) > 0.6


def check_exit(prev, curr, direction):
    """Выход при затухании."""
    return abs(curr) < 0.2


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест reversal на swing failure."""
    parts = str(param_key).split(',') if param_key else '10,0.05'
    lookback = int(parts[0]) if len(parts) > 0 else 10
    tolerance = float(parts[1]) if len(parts) > 1 else 0.05
    
    df = calc_swing_failure(df, lookback, tolerance)
    
    min_len = lookback + 10
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
