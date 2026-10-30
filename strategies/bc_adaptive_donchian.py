"""Breakout continuation на адаптивном Donchian (идея ~0201).

Гипотеза: пробой Donchian канала с адаптивным периодом (на основе ER)
даёт более ранние сигналы чем фиксированный период.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_adaptive_donchian(df, er_period=10, base_period=20):
    """Адаптивный Donchian канал на основе Efficiency Ratio.
    
    ER = |Δprice| / Σ|Δprice| — мера трендовой выраженности
    Период Donchian = base_period / ER (меньше в тренде, больше в флэте)
    
    returns: df с колонкой 'k' (позиция цены в канале)
    """
    delta = df['close'].diff(er_period).abs()
    sum_delta = df['close'].diff().abs().rolling(er_period).sum()
    er = (delta / sum_delta).replace(0, 1e-8)
    
    # Адаптивный период
    adaptive_period = (base_period / er).astype(int).clip(base_period, base_period * 4)
    
    # Donchian канал
    upper = []
    lower = []
    
    for i in range(len(df)):
        period = adaptive_period.iloc[i]
        period = min(period, i + 1)  # не больше доступных баров
        window = df['high'].iloc[max(0, i - period + 1):i + 1]
        upper.append(window.max())
        lower.append(df['low'].iloc[max(0, i - period + 1):i + 1].min())
    
    # k = нормализованная позиция цены (0 = low, 1 = high)
    width = pd.Series(upper) - pd.Series(lower)
    k = (df['close'] - pd.Series(lower)) / width.replace(0, 1e-8)
    
    df['k'] = k.values
    return df


def check_entry(prev, curr):
    """Вход при пробое вверх (curr > 0.95 и растёт)."""
    return prev > 0.90 and curr > 0.95


def check_exit(prev, curr, direction):
    """Выход при возврате к середине (curr < 0.5)."""
    return curr < 0.5


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест breakout continuation на адаптивном Donchian."""
    parts = str(param_key).split(',') if param_key else '10,20'
    er_period = int(parts[0]) if len(parts) > 0 else 10
    base_period = int(parts[1]) if len(parts) > 1 else 20
    
    df = calc_adaptive_donchian(df, er_period, base_period)
    
    min_len = base_period * 4 + 20
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
        close = df['close'].iloc[i]
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]

        if not in_pos:
            if prev_k <= 0.90 and curr_k > 0.95:
                entry_price = close
                in_pos = True
        else:
            if low <= entry_price - sl_dist:
                profit = -sl_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif high >= entry_price + tp_dist:
                profit = tp_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif check_exit(prev_k, curr_k, 'long'):
                profit = (close - entry_price) * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
    
    total_profit = sum(trades)
    return total_profit, len(trades), trades
