"""Struct Swing BOS (H1).

Idea: Break of last swing high/low confirms trend continuation (Break of Structure)
Вход: close > last swing high (long) or close < last swing low (short)
Выход: k flips from 1 to 0 (long) or -1 to 0 (short)
Отличие: Swing detection uses fractal-like pattern (5-bar confirmation)
"""
import numpy as np
import pandas as pd


def calc_struct_swing_bos(df, period=20):
    """Calculate signal. Returns df with 'k' column."""
    k = np.zeros(len(df))
    # (right) Find swing highs: bar with higher high than 2 bars on each side
    is_swing_high = np.zeros(len(df), dtype=bool)
    is_swing_low = np.zeros(len(df), dtype=bool)
    for i in range(2, len(df) - 2):
        if (df['high'].iloc[i] > df['high'].iloc[i-1] and
            df['high'].iloc[i] > df['high'].iloc[i-2] and
            df['high'].iloc[i] > df['high'].iloc[i+1] and
            df['high'].iloc[i] > df['high'].iloc[i+2]):
            is_swing_high[i] = True
        if (df['low'].iloc[i] < df['low'].iloc[i-1] and
            df['low'].iloc[i] < df['low'].iloc[i-2] and
            df['low'].iloc[i] < df['low'].iloc[i+1] and
            df['low'].iloc[i] < df['low'].iloc[i+2]):
            is_swing_low[i] = True
    # (right) Get last swing high and low within period
    last_sh = np.full(len(df), np.nan)
    last_sl = np.full(len(df), np.nan)
    for i in range(len(df)):
        window = df.iloc[max(0, i-period):i+1]
        sh = window[window.index.isin(df.index[is_swing_high])]['high'].max()
        sl = window[window.index.isin(df.index[is_swing_low])]['low'].min()
        if not np.isnan(sh):
            last_sh.iloc[i] = sh
        if not np.isnan(sl):
            last_sl.iloc[i] = sl
    # (right) k=1 when close breaks above last swing high
    k = np.where(~np.isnan(last_sh) & (df['close'] > last_sh), 1, k)
    # (right) k=-1 when close breaks below last swing low
    k = np.where(~np.isnan(last_sl) & (df['close'] < last_sl), -1, k)
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    return (prev == 0 and curr == 1) or (prev == 0 and curr == -1)


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    df = calc_struct_swing_bos(df, int(param_key))
    profit = 0
    n_trades = 0
    trade_profits = []

    sl_dist = sl_points * point
    tp_dist = tp_points * point

    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        close = df['close'].iloc[i]
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]

        if prev_k == 0 and curr_k == 1:
            entry = close
            sl_price = entry - sl_dist
            tp_price = entry + tp_dist
            for j in range(i+1, min(i+50, len(df))):
                if df['low'].iloc[j] <= sl_price:
                    profit += (sl_price - entry) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(sl_price - entry)
                    break
                elif df['high'].iloc[j] >= tp_price:
                    profit += (tp_price - entry) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(tp_price - entry)
                    break
        elif prev_k == 0 and curr_k == -1:
            entry = close
            sl_price = entry + sl_dist
            tp_price = entry - tp_dist
            for j in range(i+1, min(i+50, len(df))):
                if df['high'].iloc[j] >= sl_price:
                    profit += (entry - sl_price) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(entry - sl_price)
                    break
                elif df['low'].iloc[j] <= tp_price:
                    profit += (entry - tp_price) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(entry - tp_price)
                    break

    return (profit, n_trades, trade_profits)
