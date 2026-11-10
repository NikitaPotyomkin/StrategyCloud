"""Mom Efficiency (H1).

Idea: Efficiency ratio measures directional momentum vs total noise
Вход: Efficiency(20) > 0.5 (strong direction), trade in direction of move
Выход: k flips from 1 to 0 (long) or -1 to 0 (short)
Отличие: Uses ER = |net change| / sum of absolute changes (Kaufman-style)
"""
import numpy as np
import pandas as pd


def calc_mom_efficiency(df, period=20):
    """Calculate signal. Returns df with 'k' column."""
    k = np.zeros(len(df))
    close = df['close'].values
    # (right) Net change over period
    net_change = np.zeros(len(close))
    abs_sum = np.zeros(len(close))
    for i in range(period, len(close)):
        net_change[i] = abs(close[i] - close[i-period])
        s = 0.0
        for j in range(1, period + 1):
            s += abs(close[i-j+1] - close[i-j])
        abs_sum[i] = s
    # (right) Efficiency ratio
    er = np.zeros(len(close))
    for i in range(period, len(close)):
        if abs_sum[i] > 0:
            er[i] = net_change[i] / abs_sum[i]
        else:
            er[i] = 0
    # (right) k=1: er > 0.5 and close > close.shift(period) (uptrend)
    # (right) use manual shift instead of np.roll to avoid wrapping artifacts
    close_shifted = np.roll(close, period)
    close_shifted[:period] = np.nan
    k = np.where((er > 0.5) & (close > close_shifted), 1, k)
    # (right) k=-1: er > 0.5 and close < close.shift(period) (downtrend)
    k = np.where((er > 0.5) & (close < close_shifted), -1, k)
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Returns 'long' / 'short' / None for engine run_backtest
    if prev == 0 and curr == 1:
        return 'long'
    if prev == 0 and curr == -1:
        return 'short'
    return None


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    df = calc_mom_efficiency(df, int(param_key))
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
