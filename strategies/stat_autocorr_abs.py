"""Stat Autocorr Abs (H1).

Idea: ACF of |returns| at lag 1 > 0.2 indicates volatility clustering
Вход: ACF(|ret|,1) > 0.2 for long (vol persistence), < -0.2 for short
Выход: ACF drops below threshold
Отличие: Focuses on absolute return autocorrelation (volatility clustering pattern)
"""
import numpy as np
import pandas as pd


def _acf(values, lag):
    """Calculate autocorrelation at given lag."""
    n = len(values)
    if lag >= n - 1:
        return 0.0
    mean = np.mean(values)
    centered = values - mean
    var = np.sum(centered ** 2)
    if var < 1e-15:
        return 0.0
    cov = np.sum(centered[lag:] * centered[:-lag]) / n
    return cov / var


def calc_stat_autocorr_abs(df, period=20):
    """Calculate absolute return autocorrelation signal. Returns df with 'k' column."""
    returns = np.diff(np.log(df['close'].values))
    abs_returns = np.abs(returns)
    n = len(df)
    k = np.zeros(n)

    for i in range(period, n):
        window = abs_returns[i - period:i]
        if len(window) < 10:
            continue

        acf1 = _acf(window, 1)

        if acf1 > 0.2:
            # Volatility clustering - trend following
            # Check if recent returns are positive
            recent_ret = returns[i - 1]
            if recent_ret > 0:
                k[i] = 1
            elif recent_ret < 0:
                k[i] = -1
            else:
                k[i] = 0
        elif acf1 < -0.2:
            # Anti-persistence in volatility - mean reversion
            recent_ret = returns[i - 1]
            if recent_ret > 0:
                k[i] = -1
            elif recent_ret < 0:
                k[i] = 1
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
    df = calc_stat_autocorr_abs(df, int(param_key))
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
