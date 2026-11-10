"""Stat KS Change (H1).

Idea: Kolmogorov-Smirnov test detects regime change between two return distributions
Вход: KS p < 0.05 with recent mean > historical for long, opposite for short
Выход: KS p >= 0.05 (regimes converged)
Отличие: Nonparametric test for distribution shift in rolling windows
"""
import numpy as np
import pandas as pd


def _ks_statistic(sample1, sample2):
    """Calculate two-sample KS statistic and approximate p-value."""
    s1 = np.sort(sample1)
    s2 = np.sort(sample2)

    n1 = len(s1)
    n2 = len(s2)

    if n1 < 3 or n2 < 3:
        return 0.0, 1.0

    # Combined sorted values
    all_vals = np.concatenate([s1, s2])
    all_vals = np.unique(all_vals)

    # CDFs
    cdf1 = np.searchsorted(s1, all_vals, side='right') / n1
    cdf2 = np.searchsorted(s2, all_vals, side='right') / n2

    # KS statistic
    d_stat = np.max(np.abs(cdf1 - cdf2))

    # Approximate p-value (asymptotic)
    n_eff = (n1 * n2) / (n1 + n2)
    if n_eff < 1:
        return d_stat, 1.0

    lam = (np.sqrt(n_eff) + 0.12 + 0.11 / np.sqrt(n_eff)) * d_stat
    if lam < 0:
        lam = 0

    # Approximate using exponential tail
    p_val = 2.0 * np.exp(-2.0 * lam * lam)
    p_val = max(0.0, min(1.0, p_val))

    return d_stat, p_val


def calc_stat_ks_change(df, period=20):
    """Calculate KS regime change signal. Returns df with 'k' column."""
    returns = np.diff(np.log(df['close'].values))
    n = len(df)
    k = np.zeros(n)

    # Window sizes
    short_w = max(5, period // 3)
    long_w = period

    for i in range(long_w, n):
        # Recent window
        recent = returns[i - short_w:i]
        # Historical window
        historical = returns[i - long_w:i - short_w]

        if len(recent) < 5 or len(historical) < 10:
            continue

        if np.all(np.isnan(recent)) or np.all(np.isnan(historical)):
            continue

        d_stat, p_val = _ks_statistic(recent, historical)

        if p_val < 0.05:
            # Direction of change
            recent_mean = np.nanmean(recent)
            hist_mean = np.nanmean(historical)

            if recent_mean > hist_mean:
                k[i] = 1
            elif recent_mean < hist_mean:
                k[i] = -1
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
    df = calc_stat_ks_change(df, int(param_key))
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
