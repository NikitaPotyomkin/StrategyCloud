"""Mean Reversion: Distance Percentile (H1).

Idea: 0884 mr_distance_percentile
Вход: расстояние до MA(20) > p95(500)
Выход: p50
Отличие: Процентиль расстояния вместо абсолютного z-score
"""
import numpy as np
import pandas as pd


def calc_mr_distance_percentile(df, ma_period=20, win_period=500):
    """Процентиль расстояния цены от MA."""
    ma = df['close'].rolling(ma_period).mean()
    distance = (df['close'] - ma).abs()

    # (right) rolling percentile через apply
    p95 = distance.rolling(win_period).apply(
        lambda x: np.percentile(x, 95) if len(x) > 10 else np.nan, raw=True
    )
    p50 = distance.rolling(win_period).apply(
        lambda x: np.percentile(x, 50) if len(x) > 10 else np.nan, raw=True
    )

    sign = np.sign(df['close'] - ma)

    k = np.zeros(len(df))
    k[(distance > p95) & (sign > 0)] = 1   # цена выше MA на экстремуме
    k[(distance > p95) & (sign < 0)] = -1  # цена ниже MA на экстремуме

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
    ma_period = int(parts[0]) if len(parts) > 0 else 20
    win_period = int(parts[1]) if len(parts) > 1 else 500

    df = calc_mr_distance_percentile(df, ma_period, win_period)
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
