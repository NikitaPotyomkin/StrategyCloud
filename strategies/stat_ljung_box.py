"""Stat Ljung-Box (H1).

Idea: Ljung-Box test p-value < 0.05 indicates autocorrelation (predictable structure)
Вход: LB p < 0.05 with positive autocorrelation for long, negative for short
Выход: LB p >= 0.05 (no more predictability)
Отличие: Uses Ljung-Box Q-statistic to detect serial dependence in returns
"""
import numpy as np
import pandas as pd


def _ljung_box_stat(returns, lags):
    """Calculate Ljung-Box Q-statistic and approximate p-value."""
    n = len(returns)
    if n < lags + 10:
        return 0.0, 0.5

    mean_ret = np.mean(returns)
    centered = returns - mean_ret
    var = np.var(centered)

    if var < 1e-15:
        return 0.0, 0.5

    acf_vals = []
    for lag in range(1, lags + 1):
        if lag >= n:
            break
        cov = np.mean(centered[lag:] * centered[:-lag])
        rho = cov / var
        acf_vals.append(rho)

    if not acf_vals:
        return 0.0, 0.5

    # Q statistic
    q_stat = 0.0
    for idx, rho in enumerate(acf_vals):
        q_stat += rho ** 2 / (n - idx - 1)
    q_stat *= n * (n + 2)

    # Approximate p-value using chi-square(1) tail (conservative)
    # Using normal approximation for chi-square
    z = np.sqrt(2 * q_stat) - np.sqrt(2 * len(acf_vals) - 1)
    # Approximate p-value from normal
    p_val = 0.5 * (1 + np.erf(-z / np.sqrt(2)))

    return q_stat, max(0.0, min(1.0, p_val))


def calc_stat_ljung_box(df, period=20, lags=10):
    """Calculate Ljung-Box predictability signal. Returns df with 'k' column."""
    returns = df['close'].pct_change().dropna()
    n = len(returns)
    k = np.zeros(n)

    for i in range(lags, n):
        window = returns.iloc[max(0, i - period):i + 1]
        if len(window) < lags + 5:
            continue

        _, p_val = _ljung_box_stat(window.values, lags)

        if p_val < 0.05:
            # Check sign of first lag autocorrelation
            var_w = np.var(window.values)
            if var_w > 1e-15:
                cov = np.mean((window.values[1:] - np.mean(window)) *
                               (window.values[:-1] - np.mean(window)))
                rho1 = cov / var_w
                if rho1 > 0:
                    k[i] = 1  # positive autocorr -> trend continuation
                else:
                    k[i] = -1  # negative autocorr -> mean reversion

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
    df = calc_stat_ljung_box(df, int(param_key))
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
