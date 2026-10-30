"""Multi-indicator composite: ADX + RSI + MA (идея ~0262).

Гипотеза: сильный тренд (ADX > 25) + RSI в сторону тренда + цена выше MA
даёт надёжный сигнал продолжения.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_adx_rsi_ma(df, adx_period=14, rsi_period=14, ma_period=50):
    """Композит тренд-фильтра.
    
    returns: df с колонкой 'k' (score -1..1)
    """
    # ADX
    delta_high = df['high'].diff()
    delta_low = df['low'].diff()
    
    plus_dm = delta_high.where((delta_high > delta_low) & (delta_high > 0), 0.0)
    minus_dm = delta_low.where((delta_low > delta_high) & (delta_low > 0), 0.0)
    
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift()).abs()
    tr3 = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.rolling(adx_period).mean()
    plus_di = 100 * (plus_dm.rolling(adx_period).mean() / atr.replace(0, 1e-8))
    minus_di = 100 * (minus_dm.rolling(adx_period).mean() / atr.replace(0, 1e-8))
    
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-8)
    adx = dx.rolling(adx_period).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(rsi_period).mean()
    avg_loss = loss.rolling(rsi_period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # MA
    ma = df['close'].rolling(ma_period).mean()
    
    # Композит
    trend_up = (adx > 25) & (plus_di > minus_di) & (df['close'] > ma) & (rsi > 50)
    trend_down = (adx > 25) & (minus_di > plus_di) & (df['close'] < ma) & (rsi < 50)
    
    k = np.where(trend_up, 1.0, np.where(trend_down, -1.0, 0.0))
    
    df['k'] = k.values
    
    return df


def check_entry(prev, curr):
    """Вход при появлении трендового сигнала."""
    return prev == 0.0 and curr != 0.0


def check_exit(prev, curr, direction):
    """Выход при исчезновении."""
    return curr == 0.0


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест multi-indicator trend filter."""
    parts = str(param_key).split(',') if param_key else '14,14,50'
    adx_period = int(parts[0]) if len(parts) > 0 else 14
    rsi_period = int(parts[1]) if len(parts) > 1 else 14
    ma_period = int(parts[2]) if len(parts) > 2 else 50
    
    df = calc_adx_rsi_ma(df, adx_period, rsi_period, ma_period)
    
    min_len = max(adx_period, rsi_period, ma_period) + 10
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

        if not in_pos:
            if prev_k == 0 and curr_k == 1:
                entry_price = df['close'].iloc[i]
                in_pos = True
        else:
            if low - entry_price <= -sl_dist:
                profit = -sl_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif high - entry_price >= tp_dist:
                profit = tp_dist * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
            elif check_exit(prev_k, curr_k, 'long'):
                profit = (df['close'].iloc[i] - entry_price) * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
    
    total_profit = sum(trades)
    return total_profit, len(trades), trades
