"""Chan Donchian Pct Squeeze (H1).

Idea: Donchian channel width contracts below threshold, then price breaks out
Вход: width_pct < p15 then close > upper band (long) or close < lower band (short)
Выход: k flips from 1 to 0 (long) or -1 to 0 (short)
Отличие: Entry on breakout bar after squeeze confirmed, width measured as percentage
"""
import numpy as np
import pandas as pd


def calc_chan_donchian_pct_squeeze(df, period=20):
    """Calculate signal. Returns df with 'k' column."""
    k = np.zeros(len(df))
    upper = df['high'].rolling(period).max()
    lower = df['low'].rolling(period).min()
    mid = (upper + lower) / 2.0
    # (right) width as percentage of mid
    width = (upper - lower) / mid
    # (right) squeeze condition: width below percentile threshold
    # (right) removed: p15 = int(df['param_key']) — param_key is not a df column, would raise KeyError
    width_pct = width.rolling(100).quantile(0.15) if len(width) > 100 else width.quantile(0.15)
    squeeze = width < width_pct
    # (right) k=1: squeeze + close above upper
    k = np.where(squeeze & (df['close'] > upper.shift(1)), 1, k)
    # (right) k=-1: squeeze + close below lower
    k = np.where(squeeze & (df['close'] < lower.shift(1)), -1, k)
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
    df = calc_chan_donchian_pct_squeeze(df, int(param_key))
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
