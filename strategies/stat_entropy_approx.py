"""Stat Approx Entropy (H1).

Idea: Approximate Entropy < p30 indicates low complexity (trend-like) regime
Вход: ApEn < p30 with positive slope for long, negative for short
Выход: ApEn rises above p30 (complexity increases)
Отличие: Measures regularity in price series - low entropy = predictable trend
"""
import numpy as np
import pandas as pd


def _approx_entropy(series, m=2, r=None):
    """Calculate Approximate Entropy of a time series."""
    n = len(series)
    if n < m + 10:
        return 0.0

    if r is None:
        r = 0.2 * np.std(series)

    if r < 1e-12:
        return 0.0

    # Create embedded vectors
    def _count_matches(x, vecs, r):
        count = 0
        for v in vecs:
            max_diff = np.max(np.abs(np.array(x) - np.array(v)))
            if max_diff <= r:
                count += 1
        return count

    vecs_m = []
    for i in range(n - m):
        vecs_m.append(series[i:i + m])

    vecs_m1 = []
    for i in range(n - m - 1):
        vecs_m1.append(series[i:i + m + 1])

    # Count matches for dimension m
    B = np.zeros(n - m)
    for i in range(n - m):
        B[i] = _count_matches(vecs_m[i], vecs_m, r) / (n - m)

    # Count matches for dimension m+1
    A = np.zeros(n - m - 1)
    for i in range(n - m - 1):
        A[i] = _count_matches(vecs_m1[i], vecs_m1, r) / (n - m - 1)

    # Avoid log(0)
    B_avg = np.mean(B)
    A_avg = np.mean(A)

    if B_avg < 1e-10 or A_avg < 1e-10:
        return 0.0

    apen = -np.log(A_avg / B_avg)
    return apen


def calc_stat_entropy_approx(df, period=20):
    """Calculate approximate entropy signal. Returns df with 'k' column."""
    returns = np.diff(np.log(df['close'].values))
    n = len(df)
    k = np.zeros(n)

    # Store ApEn history for percentile tracking
    apen_history = []

    for i in range(period, n):
        window = returns[i - period:i]
        if len(window) < 20:
            continue

        apen = _approx_entropy(window, m=2, r=None)
        apen_history.append(apen)

        if len(apen_history) < 30:
            k[i] = 0
            continue

        sorted_apen = sorted(apen_history)
        p30_idx = int(0.3 * len(sorted_apen))
        p30_val = sorted_apen[min(p30_idx, len(sorted_apen) - 1)]

        if apen < p30_val:
            # Low complexity - check trend direction
            recent = returns[i - 5:i]
            slope = np.polyfit(np.arange(len(recent)), recent, 1)[0]
            if slope > 0:
                k[i] = 1
            elif slope < 0:
                k[i] = -1
            else:
                k[i] = 0
        else:
            k[i] = 0

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
    df = calc_stat_entropy_approx(df, int(param_key))
    profit = 0
    n_trades = 0
    trade_profits = []

    sl_dist = sl_points * point
    tp_dist = tp_points * point

    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i - 1]
        curr_k = df['k'].iloc[i]
        close = df['close'].iloc[i]
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]

        if prev_k == 0 and curr_k == 1:
            entry = close
            sl_price = entry - sl_dist
            tp_price = entry + tp_dist
            for j in range(i + 1, min(i + 50, len(df))):
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
            for j in range(i + 1, min(i + 50, len(df))):
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
