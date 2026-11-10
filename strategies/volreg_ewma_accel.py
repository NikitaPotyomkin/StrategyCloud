"""Volatility Regime: EWMA Vol Acceleration (H1).

Idea: 0006 volreg_ewma_accel
Вход: EWMA-vol(0.94) выросла 2x к медиане(200)
Выход: return ниже 8 баров
Отличие: EWMA-волатильность вместо ATR, экспоненциальное сглаживание
"""
import numpy as np
import pandas as pd


def calc_volreg_ewma_accel(df, period=50):
    """EWMA volatility acceleration."""
    ret = df['close'].pct_change()

    # (right) EWMA vol с alpha=0.94
    alpha = 0.94
    ewma_vol = pd.Series(0.0, index=df.index)
    ewma_vol.iloc[0] = ret.iloc[0].abs()
    for i in range(1, len(df)):
        ewma_vol.iloc[i] = alpha * ret.iloc[i].abs() + (1 - alpha) * ewma_vol.iloc[i-1]

    # медиана за period баров
    med_vol = ewma_vol.rolling(period).median()

    ratio = ewma_vol / (med_vol + 1e-12)

    k = np.zeros(len(df))
    k[ratio > 2.0] = 1   # волатильность выросла 2x
    k[ratio < 0.5] = -1  # волатильность упала

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
    df = calc_volreg_ewma_accel(df, int(param_key))
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
