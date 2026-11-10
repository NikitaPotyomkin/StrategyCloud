"""Stat Half-Life (H1).

Idea: Half-life of mean reversion < 10 bars indicates fast-reverting regime
Вход: half_life < 10 and price below mean for long, above for short
Выход: half_life >= 10 or price crosses mean
Отличие: Uses OLS on price changes vs lagged price deviation for half-life estimation
"""
import numpy as np
import pandas as pd


def _estimate_half_life(prices, window):
    """Estimate half-life of mean reversion using OLS."""
    if len(prices) < window + 5:
        return 999.0

    log_prices = np.log(prices)
    delta = np.diff(log_prices[-window:])
    lagged = log_prices[-window - 1:-1] - np.mean(log_prices[-window:])

    # Remove NaNs
    mask = ~(np.isnan(delta) | np.isnan(lagged))
    delta = delta[mask]
    lagged = lagged[mask]

    if len(delta) < 10:
        return 999.0

    # OLS: delta = alpha + beta * lagged
    x_mean = np.mean(lagged)
    y_mean = np.mean(delta)

    ss_xy = np.sum((lagged - x_mean) * (delta - y_mean))
    ss_xx = np.sum((lagged - x_mean) ** 2)

    if ss_xx < 1e-15:
        return 999.0

    beta = ss_xy / ss_xx

    # Half-life = -ln(2) / beta (for negative beta = mean reversion)
    if beta >= 0:
        return 999.0

    half_life = -np.log(2.0) / beta
    return half_life


def calc_stat_half_life(df, period=20):
    """Calculate half-life mean reversion signal. Returns df with 'k' column."""
    n = len(df)
    k = np.zeros(n)

    for i in range(period, n):
        window_prices = df['close'].iloc[i - period:i + 1].values
        half_life = _estimate_half_life(window_prices, period)

        if half_life < 10:
            # Check price position relative to mean
            current_price = df['close'].iloc[i]
            mean_price = np.mean(window_prices)

            if current_price < mean_price:
                k[i] = 1  # below mean, mean-reverting up
            elif current_price > mean_price:
                k[i] = -1  # above mean, mean-reverting down
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
    df = calc_stat_half_life(df, int(param_key))
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
