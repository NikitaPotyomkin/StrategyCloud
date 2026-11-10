"""Stat LZ Complexity (H1).

Idea: Lempel-Ziv complexity falling indicates increasing regularity (trend forming)
Вход: LZ complexity declining for 3+ bars with positive price change for long
Выход: LZ complexity stops declining or price reverses
Отличие: Tracks compression complexity of discretized return sequence
"""
import numpy as np
import pandas as pd


def _lempel_ziv_complexity(sequence):
    """Calculate Lempel-Ziv complexity of a binary sequence."""
    if not sequence or len(sequence) < 4:
        return 0.0

    n = len(sequence)
    complexity = 1
    i = 0
    j = 1
    current_substring = sequence[0]

    while j < n:
        if j + 1 < n and sequence[j] == sequence[j - 1]:
            # Continue current substring
            j += 1
            continue

        # Try to extend the current substring
        found = False
        for k in range(1, i + 2):
            # Check if substring starting at position (j-k+1) matches
            prefix = sequence[max(0, j - k + 1):j + 1]
            if prefix in sequence[:j]:
                found = True
                break

        if not found:
            complexity += 1

        j += 1

    # Normalize
    normalized = complexity / np.sqrt(n) if n > 0 else 0.0
    return normalized


def _discretize_returns(returns, n_symbols=2):
    """Discretize returns into symbols."""
    if len(returns) < n_symbols + 1:
        return np.zeros(len(returns))

    abs_ret = np.abs(returns)
    threshold = np.median(abs_ret)

    symbols = np.zeros(len(returns))
    for i in range(len(returns)):
        if returns[i] > threshold:
            symbols[i] = 1
        elif returns[i] < -threshold:
            symbols[i] = 2
        else:
            symbols[i] = 0

    return symbols


def calc_stat_lz_complexity(df, period=20):
    """Calculate Lempel-Ziv complexity signal. Returns df with 'k' column."""
    returns = np.diff(np.log(df['close'].values))
    n = len(df)
    k = np.zeros(n)

    # Track LZ complexity history
    lz_history = []

    for i in range(period, n):
        window = returns[i - period:i]
        if len(window) < 15:
            continue

        symbols = _discretize_returns(window, n_symbols=2)
        lz = _lempel_ziv_complexity(symbols)
        lz_history.append((i, lz))

        if len(lz_history) < 5:
            k[i] = 0
            continue

        # Check if LZ complexity is falling
        recent_lz = [x[1] for x in lz_history[-5:]]
        if len(recent_lz) >= 3:
            # Check if declining for 3+ bars
            declining = all(recent_lz[j] >= recent_lz[j + 1]
                           for j in range(len(recent_lz) - 1))

            if declining:
                # Check price direction
                recent_closes = df['close'].iloc[i - 5:i + 1].values
                if len(recent_closes) >= 3:
                    slope = np.polyfit(np.arange(len(recent_closes)),
                                       recent_closes, 1)[0]
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
        else:
            k[i] = 0

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
    df = calc_stat_lz_complexity(df, int(param_key))
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
