"""Stat Permutation Entropy (H1).

Idea: Permutation Entropy < p25 indicates ordered structure (strong trend)
Вход: PE < p25 with price slope positive for long, negative for short
Выход: PE rises above p25 (structure breaks)
Отличие: Uses ordinal patterns to measure complexity of price ordering
"""
import numpy as np
import pandas as pd


def _permutation_entropy(series, delay=1, dimension=3):
    """Calculate permutation entropy of a time series."""
    n = len(series)
    if n < dimension:
        return 0.0

    max_entropy = np.log(np.math.factorial(dimension))
    if max_entropy < 1e-12:
        return 0.0

    # Count ordinal pattern frequencies
    pattern_counts = {}
    n_patterns = np.math.factorial(dimension)

    for i in range(n - dimension * delay):
        # Extract embedding vector
        vec = series[i:i + dimension * delay:delay]
        # Get ordinal pattern (rank indices)
        pattern = tuple(np.argsort(vec))
        pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

    total = sum(pattern_counts.values())
    if total < 1:
        return 0.0

    # Calculate entropy
    entropy = 0.0
    for count in pattern_counts.values():
        p = count / total
        if p > 0:
            entropy -= p * np.log(p)

    # Normalize
    pe = entropy / max_entropy
    return pe


def calc_stat_permutation_entropy(df, period=20):
    """Calculate permutation entropy signal. Returns df with 'k' column."""
    closes = df['close'].values
    n = len(df)
    k = np.zeros(n)

    # Store PE history for percentile tracking
    pe_history = []

    for i in range(period, n):
        window = closes[i - period:i]
        if len(window) < 15:
            continue

        pe = _permutation_entropy(window, delay=1, dimension=3)
        pe_history.append(pe)

        if len(pe_history) < 30:
            k[i] = 0
            continue

        sorted_pe = sorted(pe_history)
        p25_idx = int(0.25 * len(sorted_pe))
        p25_val = sorted_pe[min(p25_idx, len(sorted_pe) - 1)]

        if pe < p25_val:
            # Low permutation entropy - ordered/trending
            recent = closes[i - 10:i]
            if len(recent) >= 5:
                slope = np.polyfit(np.arange(len(recent)), recent, 1)[0]
                if slope > 0:
                    k[i] = 1
                elif slope < 0:
                    k[i] = -1
                else:
                    k[i] = 0
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
    df = calc_stat_permutation_entropy(df, int(param_key))
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
