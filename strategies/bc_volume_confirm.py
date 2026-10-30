"""Breakout continuation на объёмном подтверждении (идея ~0212).

Гипотеза: пробой диапазона с объёмом > p80 надёжнее ведёт к продолжению.
Без объёма — ложный пробой.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_volume_breakout(df, range_period=20, vol_period=60, vol_pct=80):
    """Пробой диапазона с объёмным фильтром.
    
    returns: df с колонкой 'k' (объёмный пробой = 1, иначе 0)
    """
    # Диапазон
    high_range = df['high'].rolling(range_period).max()
    low_range = df['low'].rolling(range_period).min()
    
    # Объём в перцентилях
    vol_pctile = df['volume'].rolling(vol_period).rank(pct=True)
    
    # Пробой + объём
    k = np.where(
        (df['close'] > high_range) & (vol_pctile > vol_pct / 100.0),
        1.0,
        np.where(
            (df['close'] < low_range) & (vol_pctile > vol_pct / 100.0),
            -1.0,
            0.0
        )
    )
    
    df['k'] = k
    
    return df


def check_entry(prev, curr):
    """Вход при появлении сигнала пробоя (curr != 0)."""
    return prev == 0.0 and curr != 0.0


def check_exit(prev, curr, direction):
    """Выход при исчезновении сигнала (curr == 0)."""
    return curr == 0.0


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Бэктест breakout continuation с объёмным фильтром."""
    parts = str(param_key).split(',') if param_key else '20,60,80'
    parts = parts.split('/')
    range_period = int(parts[0]) if len(parts) > 0 else 20
    vol_period = int(parts[1]) if len(parts) > 1 else 60
    vol_pct = int(parts[2]) if len(parts) > 2 else 80
    
    df = calc_volume_breakout(df, range_period, vol_period, vol_pct)
    
    min_len = max(range_period, vol_period) + 10
    if len(df) < min_len:
        return 0, 0, []
    
    trades = []
    in_pos = False
    entry_price = 0.0
    direction = 0  # 1 = long, -1 = short
    
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
                entry_price = close
                direction = 1
                in_pos = True
            elif prev_k == 0 and curr_k == -1:
                entry_price = close
                direction = -1
                in_pos = True
        else:
            if direction > 0:
                if low <= entry_price - sl_dist:
                    profit = -sl_dist * tick_value * sim_lot
                    trades.append(profit)
                    in_pos = False
                elif high >= entry_price + tp_dist:
                    profit = tp_dist * tick_value * sim_lot
                    trades.append(profit)
                    in_pos = False
            else:
                if high >= entry_price + sl_dist:
                    profit = -sl_dist * tick_value * sim_lot
                    trades.append(profit)
                    in_pos = False
                elif low <= entry_price - tp_dist:
                    profit = tp_dist * tick_value * sim_lot
                    trades.append(profit)
                    in_pos = False

            if check_exit(prev_k, curr_k, direction):
                if direction > 0:
                    profit = (close - entry_price) * tick_value * sim_lot
                else:
                    profit = (entry_price - close) * tick_value * sim_lot
                trades.append(profit)
                in_pos = False
    
    total_profit = sum(trades)
    return total_profit, len(trades), trades
