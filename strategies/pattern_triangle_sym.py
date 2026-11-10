"""Pattern Triangle Sym (H1).

Idea: Symmetric triangle formed by converging highs and lows, trade breakout
Вход: highs decreasing and lows increasing over period, then close > upper or < lower
Выход: k flips from 1 to 0 (long) or -1 to 0 (short)
Отличие: Detects symmetric convergence pattern before breakout
"""
import numpy as np
import pandas as pd


def calc_pattern_triangle_sym(df, period=20):
    """Calculate signal. Returns df with 'k' column."""
    k = np.zeros(len(df))
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    # (right) Rolling max high and min low
    rolling_high = df['high'].rolling(period).max()
    rolling_low = df['low'].rolling(period).min()
    # (right) Check for converging pattern: highs decreasing, lows increasing
    # (right) Compare first half highs to second half highs
    is_converging = np.zeros(len(df), dtype=bool)
    for i in range(period, len(df)):
        window_high = high[i-period:i]
        window_low = low[i-period:i]
        # (right) Split into halves
        half = period // 2
        first_highs = window_high[:half]
        second_highs = window_high[half:]
        first_lows = window_low[:half]
        second_lows = window_low[half:]
        # (right) Highs decreasing, lows increasing
        if (np.mean(second_highs) < np.mean(first_highs) and
            np.mean(second_lows) > np.mean(first_lows)):
            is_converging[i] = True
    # (right) k=1: converging + close above rolling high
    k = np.where(is_converging & (close > rolling_high.shift(1)), 1, k)
    # (right) k=-1: converging + close below rolling low
    k = np.where(is_converging & (close < rolling_low.shift(1)), -1, k)
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
    df = calc_pattern_triangle_sym(df, int(param_key))
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
