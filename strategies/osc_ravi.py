"""Oscillator: RAVI (H1).

Idea: 0360 osc_ravi
Вход: RAVI (ROC MA 7/65) > 0.3%
Выход: RAVI < -0.3%
Отличие: ROC на скользящих средних — скорость изменения скорости
"""
import numpy as np
import pandas as pd


def calc_osc_ravi(df, fast=7, slow=65):
    """ROC Average Velocity Index."""
    roc = df['close'].pct_change(fast)
    roc_slow = df['close'].pct_change(slow)

    ma_fast = roc.rolling(fast).mean()
    ma_slow = roc_slow.rolling(slow).mean()

    ravi = (ma_fast - ma_slow) * 100  # в процентах

    k = np.zeros(len(df))
    k[ravi > 0.3] = 1
    k[ravi < -0.3] = -1

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
    parts = str(param_key).split(',') if isinstance(param_key, str) else [str(param_key)]
    fast = int(parts[0]) if len(parts) > 0 else 7
    slow = int(parts[1]) if len(parts) > 1 else 65

    df = calc_osc_ravi(df, fast, slow)
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
