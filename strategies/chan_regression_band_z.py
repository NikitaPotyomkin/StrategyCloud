"""Chan Regression Band Z (H1).

Idea: Price deviates from linear regression by more than 2 standard deviations
Вход: z-score of residual > 2 (short) or < -2 (long), then mean reversion
Выход: k flips from 1 to 0 (long) or -1 to 0 (short)
Отличие: Uses OLS regression residuals normalized by their std (z-score)
"""
import numpy as np
import pandas as pd


def calc_chan_regression_band_z(df, period=20):
    """Calculate signal. Returns df with 'k' column."""
    k = np.zeros(len(df))
    x = np.arange(period, dtype=float)
    closes = df['close'].values
    # (right) Compute rolling OLS regression
    for i in range(period, len(df)):
        window_c = closes[i-period:i]
        # (right) OLS: y = a + b*x
        x_mean = x.mean()
        y_mean = window_c.mean()
        ss_xy = np.sum((x - x_mean) * (window_c - y_mean))
        ss_xx = np.sum((x - x_mean) ** 2)
        if ss_xx == 0:
            continue
        b = ss_xy / ss_xx
        a = y_mean - b * x_mean
        # (right) Predicted value for last bar
        predicted = a + b * (period - 1)
        actual = closes[i-1]
        # (right) Residual and its std
        residuals = window_c - (a + b * x)
        resid_std = np.std(residuals)
        if resid_std == 0:
            continue
        z = (actual - predicted) / resid_std
        # (right) k=1: z < -2 (price below regression, mean reversion up)
        if z < -2:
            k[i] = 1
        # (right) k=-1: z > 2 (price above regression, mean reversion down)
        elif z > 2:
            k[i] = -1
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
    df = calc_chan_regression_band_z(df, int(param_key))
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
