"""Reversal на liquidity sweep (идея ~0126).

Гипотеза: прокол экстремума с быстрым возвратом внутрь диапазона
— сигнал разворота. Стопы трейдеров на экстремуме сняты.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_liquidity_sweep(df, lookback=20):
    """Ликвидационный прокол + возврат.
    
    returns: df с колонкой 'k' (сила сигнала sweep)
    """
    high_extreme = df['high'].rolling(lookback).max().shift(1)
    low_extreme = df['low'].rolling(lookback).min().shift(1)
    
    # Proкол выше экстремума, закрытие ниже
    bearish_sweep = (df['high'] > high_extreme) & (df['close'] < high_extreme)
    
    # Прокол ниже экстремума, закрытие выше
    bullish_sweep = (df['low'] < low_extreme) & (df['close'] > low_extreme)
    
    # Сила сигнала: насколько далеко закрытие внутри диапазона
    range_val = df['high'] - df['low']
    
    k = np.where(
        bearish_sweep,
        -(df['high'] - df['close']) / range_val.replace(0, 1e-8),
        np.where(
            bullish_sweep,
            (df['close'] - df['low']) / range_val.replace(0, 1e-8),
            0.0
        )
    )
    
    df['k'] = k
    
    return df


def check_entry(prev, curr):
    """Вход при появлении sweep-сигнала (curr > 0.5)."""
    return prev < 0.5 and curr > 0.5


def check_exit(prev, curr, direction):
    """Выход при затухании сигнала."""
    return curr < 0.2


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест reversal на liquidity sweep."""
    lookback = int(param_key) if param_key else 20
    df = calc_liquidity_sweep(df, lookback)
    
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
