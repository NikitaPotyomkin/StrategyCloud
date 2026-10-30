"""Advanced stat: Fractal Dimension regime (идея ~0292).

Гипотеза: фрактальная размерность Холла измеряет "сглаженность" тренда:
FD < 0.7 — сильный тренд (следовать)
FD > 1.3 — шум (не торговать)
0.7 < FD < 1.0 — слабый тренд (осторожно)

H1 OHLC только. SL/TP в пунктах символа (sl_points * point).
Спред в этой стратегии не моделируется — как и раньше; для сравнения семейств
это надо помнить (у большинства стратегий проекта spread_points учитывается).
"""
import numpy as np
import pandas as pd


def calc_fractal_dimension(df, period=20):
    """Фрактальная размерность Холла (Hurst-based).
    
    FD = 2 - H
    
    returns: df с колонкой 'k' (fractal dimension)
    """
    returns = df['close'].pct_change().dropna()
    
    fd_vals = []
    
    for i in range(len(returns)):
        if i < period:
            fd_vals.append(1.0)
            continue
        
        window = returns.iloc[i - period:i].values
        
        # Mean and standard deviation
        mean_ret = np.mean(window)
        std_ret = np.std(window)
        
        if std_ret < 1e-8:
            fd_vals.append(1.0)
            continue
        
        # Log return variance
        log_var = np.log(std_ret ** 2 + 1e-16)
        
        # H approximation через scaling
        # Используем simple R/S approach
        cum_dev = np.cumsum(window - mean_ret)
        r = np.max(cum_dev) - np.min(cum_dev)
        s = std_ret * np.sqrt(period)
        
        if s < 1e-8 or r < 1e-8:
            fd_vals.append(1.0)
            continue
        
        rs_ratio = r / s
        h = np.log(rs_ratio + 1e-16) / np.log(np.sqrt(period) + 1e-16)
        h = np.clip(h, 0.0, 1.0)
        
        # FD = 2 - H
        fd = 2.0 - h
        
        fd_vals.append(fd)
    
    # ВАЖНО: pct_change().dropna() короче df ровно на одну строку (первая),
    # поэтому len(fd_vals) = len(df) - 1. Прямое df['k'] = np.array(fd_vals)
    # падало с "Length of values (1456) does not match length of index (1457)"
    # и семейство выпадало из чекпойнта без журналов сделок.
    df['k'] = np.concatenate(([1.0], np.asarray(fd_vals, dtype=float)))
    
    return df


def check_entry(prev, curr):
    """Вход при сильном тренде (curr < 0.8)."""
    return prev > 0.8 and curr < 0.8


def check_exit(prev, curr, direction):
    """Выход при росте шума (curr > 1.3)."""
    return curr > 1.3


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест на fractal dimension."""
    period = int(param_key) if param_key else 20
    df = calc_fractal_dimension(df, period)
    
    min_len = period + 10
    if len(df) < min_len:
        return 0, 0, []
    
    # Деньги за 1 пункт цены. tick_size на брокерах металлов = 0.0001 (серебро),
    # поэтому без деления на tick_size прибыль завышалась в 10 000 раз.
    _ts = float(tick_size) if tick_size else float(point)
    if _ts <= 0:
        return 0, 0, []
    
    trades = []
    in_pos = False
    entry_price = 0.0
    
    # SL/TP в пунктах ЦЕНЫ. Раньше при spread_points > 0 подставлялся он сам,
    # из-за чего sl_dist = sl_points * spread_points (десятки тысяч пунктов) —
    # стопы не срабатывали никогда.
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        close = df['close'].iloc[i]
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]

        if not in_pos:
            if prev_k == 0 and curr_k == 1:
                if check_entry(prev_k, curr_k):
                    entry_price = close
                    in_pos = True
        else:
            if low - entry_price <= -sl_dist:
                profit = -(sl_dist / _ts) * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif high - entry_price >= tp_dist:
                profit = (tp_dist / _ts) * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif check_exit(prev_k, curr_k, 'long'):
                profit = ((close - entry_price) / _ts) * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
    
    total_profit = sum(trades)
    return total_profit, len(trades), trades
