"""VolProf Vol Imbalance (H1).

Idea: Volume imbalance between up-bars and down-bars signals institutional activity
Вход: up_volume / down_volume > 1.5 (buying pressure) or < 0.67 (selling pressure)
Выход: k flips from 1 to 0 (long) or -1 to 0 (short)
Отличие: Uses volume-weighted classification of bars as up or down
"""
import numpy as np
import pandas as pd


def calc_volprof_vol_imbalance(df, period=20):
    """Calculate signal. Returns df with 'k' column."""
    k = np.zeros(len(df))
    close = df['close'].values
    open_ = df['open'].values
    volume = df['volume'].values
    # (right) Classify bars as up or down
    up_vol = np.zeros(len(close))
    down_vol = np.zeros(len(close))
    for i in range(len(close)):
        if close[i] >= open_[i]:
            up_vol[i] = volume[i]
        else:
            down_vol[i] = volume[i]
    # (right) Rolling sums over period
    up_vol_sum = np.zeros(len(close))
    down_vol_sum = np.zeros(len(close))
    for i in range(period, len(close)):
        up_vol_sum[i] = np.sum(up_vol[i-period:i])
        down_vol_sum[i] = np.sum(down_vol[i-period:i])
    # (right) Imbalance ratio
    ratio = np.zeros(len(close))
    for i in range(period, len(close)):
        if down_vol_sum[i] > 0:
            ratio[i] = up_vol_sum[i] / down_vol_sum[i]
        else:
            ratio[i] = 2.0  # (right) all up bars, extreme bullish
    # (right) k=1: ratio > 1.5 (buying pressure)
    k = np.where(ratio > 1.5, 1, k)
    # (right) k=-1: ratio < 0.67 (selling pressure)
    k = np.where(ratio < 0.67, -1, k)
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
    df = calc_volprof_vol_imbalance(df, int(param_key))
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
