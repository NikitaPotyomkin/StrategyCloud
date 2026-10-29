"""Mean reversion на z-score диапазона (идея ~0241).

Гипотеза: когда ширина диапазона (high-low) отклоняется > 2σ от медианы,
рынок перегрет и вероятен откат к среднему.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_zscore_range(df, period=40):
    """Расчёт z-score ширины диапазона.
    
    df: OHLCV
    period: окно для расчёта медианы и σ
    returns: df с колонкой 'k' (z-score range)
    """
    width = df['high'] - df['low']
    mean_w = width.rolling(period).mean()
    std_w = width.rolling(period).std()
    z = (width - mean_w) / std_w
    df['k'] = z.values
    return df


def check_entry(prev, curr):
    """Вход при экстремальном z-score <-2 (сильный бар, реверс вниз)."""
    return prev < -2.0 and curr < -2.0


def check_exit(prev, curr, direction):
    """Выход при возврате к нулю (curr > -0.5)."""
    return curr > -0.5


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест mean reversion на z-score диапазона.
    
    param_key: period (окно расчёта z-score)
    """
    period = int(param_key) if param_key else 40
    df = calc_zscore_range(df, period)
    
    min_len = period + 5
    if len(df) < min_len:
        return 0, 0, []
    
    capital = 10000.0
    trades = []
    in_pos = False
    entry_price = 0.0
    sl_hit = False
    tp_hit = False
    
    sl_dist = sl_points * spread_points if spread_points > 0 else sl_points * point
    tp_dist = tp_points * spread_points if spread_points > 0 else tp_points * point
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]
        close = df['close'].iloc[i]
        
        if not in_pos:
            if check_entry(prev_k, curr_k):
                entry_price = close
                in_pos = True
                sl_hit = False
                tp_hit = False
        else:
            # Проверяем SL/TP по истории бара
            if close - entry_price <= -sl_dist:
                sl_hit = True
                profit = -sl_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif close - entry_price >= tp_dist:
                tp_hit = True
                profit = tp_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif check_exit(prev_k, curr_k, 'long'):
                profit = (close - entry_price) * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
    
    total_profit = sum(trades)
    return total_profit, len(trades), trades
