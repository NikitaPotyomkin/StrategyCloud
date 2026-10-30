"""Volatility Regime: Parkinson Ratio (H1).

Idea: 0001 volreg_parkinson_ratio
Вход: Parkinson(20)/Parkinson(100) > thr и close в верхней трети бара
Выход: trail 2xATR
Отличие: оценщик волатильности Parkinson (high/low), а не ATR (close-open)
"""
import numpy as np
import pandas as pd


def calc_volreg_parkinson_ratio(df, period=20):
    """Расчёт сигнала volreg_parkinson_ratio.
    
    df: DataFrame с колонками ['open','high','low','close','volume']
    period: период для Parkinson(20) и Parkinson(100)
    returns: df с колонкой 'k' ∈ {-1, 0, 1}
    """
    # Parkinson volatility: sqrt( ln(H/L)^2 )
    hl_ratio = np.log(df['high'] / df['low']) ** 2
    park_20 = hl_ratio.rolling(period).mean() ** 0.5
    park_100 = hl_ratio.rolling(100).mean() ** 0.5
    
    ratio = park_20 / park_100.replace(0, np.nan)
    
    # close в верхней трети бара
    upper_third = df['close'] > (df['high'] - (df['high'] - df['low']) / 3)
    
    # signal
    k = np.zeros(len(df))
    k[(ratio > 1.5) & upper_third] = 1
    k[(ratio < 0.8) & (df['close'] < (df['low'] + (df['high'] - df['low']) / 3))] = -1
    
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    """Вход: сигнал меняется с 0/−1 на +1 или с 0/+1 на −1."""
    if prev == 0 and curr == 1:
        return True
    if prev == 0 and curr == -1:
        return True
    return False


def check_exit(prev, curr, direction):
    """Выход: сигнал разворачивается."""
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    """Бэктест volreg_parkinson_ratio.
    
    param_key: период (20 по умолчанию)
    """
    df = calc_volreg_parkinson_ratio(df, int(param_key))
    
    profit = 0
    n_trades = 0
    trade_profits = []
    
    # SL/TP в пунктах (не в спредах)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    
    position = None  # ('long'|'short', entry_price)
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]
        close = df['close'].iloc[i]
        
        if position is None:
            if check_entry(prev_k, curr_k):
                entry = close
                position = ('long' if curr_k == 1 else 'short', entry)
        else:
            direction, entry = position
            
            if direction == 'long':
                sl_price = entry - sl_dist
                tp_price = entry + tp_dist
                if low <= sl_price:
                    pnl = (sl_price - entry) * sim_lot * tick_value
                    profit += pnl
                    n_trades += 1
                    trade_profits.append(pnl)
                    position = None
                elif high >= tp_price:
                    pnl = (tp_price - entry) * sim_lot * tick_value
                    profit += pnl
                    n_trades += 1
                    trade_profits.append(pnl)
                    position = None
            else:
                sl_price = entry + sl_dist
                tp_price = entry - tp_dist
                if high >= sl_price:
                    pnl = (entry - sl_price) * sim_lot * tick_value
                    profit += pnl
                    n_trades += 1
                    trade_profits.append(pnl)
                    position = None
                elif low <= tp_price:
                    pnl = (entry - tp_price) * sim_lot * tick_value
                    profit += pnl
                    n_trades += 1
                    trade_profits.append(pnl)
                    position = None
    
    return (profit, n_trades, trade_profits)
