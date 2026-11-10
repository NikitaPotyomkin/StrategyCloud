"""Stat Anderson-Darling (H1).

Idea: Anderson-Darling test rejects normality (p < 0.05) indicating fat tails / extremes
Вход: AD p < 0.05 with skew > 0 for long, skew < 0 for short
Выход: AD p >= 0.05 (returns become normal again)
Отличие: Uses Anderson-Darling test for normality to detect fat-tail regimes
"""
import numpy as np
import pandas as pd


def _anderson_darling_stat(returns):
    """Calculate Anderson-Darling test statistic and approximate p-value."""
    n = len(returns)
    if n < 10:
        return 0.0, 1.0

    sorted_x = np.sort(returns)
    mean_x = np.mean(sorted_x)
    std_x = np.std(sorted_x, ddof=1)

    if std_x < 1e-12:
        return 0.0, 1.0

    # Standardize
    z = (sorted_x - mean_x) / std_x

    # CDF of standard normal
    # Using error function: Phi(x) = 0.5 * (1 + erf(x/sqrt(2)))
    Phi = 0.5 * (1 + np.erf(z / np.sqrt(2)))

    # AD statistic
    # A^2 = -n - (1/n) * sum((2i-1)(ln(F_i) + ln(1-F_{n-i+1})))
    i_arr = np.arange(1, n + 1)
    log_terms = 0.0
    for i in range(n):
        fi = Phi[i]
        fi = max(1e-10, min(1 - 1e-10, fi))
        fn_i = Phi[n - 1 - i]
        fn_i = max(1e-10, min(1 - 1e-10, fn_i))
        log_terms += (2 * i_arr[i] - 1) * (np.log(fi) + np.log(fn_i))

    ad_stat = -n - log_terms / n

    # Approximate p-value using empirical relationship
    # For AD test, use known critical values approximation
    if ad_stat < 0.5:
        p_val = 0.8
    elif ad_stat < 1.0:
        p_val = 0.5 - (ad_stat - 0.5) * 0.3
    elif ad_stat < 2.0:
        p_val = 0.2 - (ad_stat - 1.0) * 0.1
    elif ad_stat < 3.0:
        p_val = 0.1 - (ad_stat - 2.0) * 0.05
    elif ad_stat < 5.0:
        p_val = 0.05 - (ad_stat - 3.0) * 0.02
    else:
        p_val = max(0.0, 0.01 - (ad_stat - 5.0) * 0.002)

    p_val = max(0.0, min(1.0, p_val))

    return ad_stat, p_val


def calc_stat_anderson_darling(df, period=20):
    """Calculate Anderson-Darling normality signal. Returns df with 'k' column."""
    returns = np.diff(np.log(df['close'].values))
    n = len(df)
    k = np.zeros(n)

    for i in range(period, n):
        window = returns[i - period:i]
        if len(window) < 15:
            continue

        ad_stat, p_val = _anderson_darling_stat(window)

        if p_val < 0.05:
            # Non-normal - check skewness for direction
            skew = np.mean(((window - np.mean(window)) / np.std(window, ddof=1)) ** 3)

            if np.isnan(skew):
                k[i] = 0
            elif skew > 0.3:
                k[i] = 1  # positive skew -> long
            elif skew < -0.3:
                k[i] = -1  # negative skew -> short
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
    df = calc_stat_anderson_darling(df, int(param_key))
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
