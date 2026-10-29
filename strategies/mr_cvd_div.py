"""Mean reversion на дивергенции CVD и цены (идея ~0087).

Гипотеза: когда CVD растёт, а цена падает — это сигнал разворота вверх.
Объём подтверждает движение денег, цена следует за "умными деньгами".

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_cvd(df, period=50):
    """Расчёт CVD (Cumulative Volume Delta) и z-score.
    
    CVD = накопленная сумма (close-open)/range * volume
    df: OHLCV
    period: окно для нормализации
    returns: df с колонкой 'k' (нормализованная дивергенция)
    """
    # Delta = знак закрытия * объём
    range_val = (df['high'] - df['low']).replace(0, 1e-8)
    delta = ((df['close'] - df['open']) / range_val) * df['volume']
    
    # CVD = скользящая сумма delta
    cvd = delta.rolling(period).sum()
    
    # Нормализация: z-score CVD
    mean_cvd = cvd.rolling(period * 2).mean()
    std_cvd = cvd.rolling(period * 2).std()
    k = (cvd - mean_cvd) / std_cvd
    
    df['k'] = k.values
    return df


def check_entry(prev, curr):
    """Вход при экстремальной негативной дивергенции (curr < -1.5 и улучшается)."""
    return prev < -1.5 and curr > prev  # начинает расти


def check_exit(prev, curr, direction):
    """Выход при возврате к нулю."""
    return curr > 0.0


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест mean reversion на дивергенции CVD."""
    period = int(param_key) if param_key else 50
    df = calc_cvd(df, period)
    
    min_len = period * 2 + 10
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
