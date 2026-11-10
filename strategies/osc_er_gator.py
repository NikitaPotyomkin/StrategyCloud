"""Oscillator: Gator (H1).

Idea: 0360 osc_er_gator
Вход: Gator — BB width vs Keltner, расширение
Выход: сужение
Отличие: Визуальный осциллятор для сжатия/расширения волатильности
"""
import numpy as np
import pandas as pd


def calc_osc_er_gator(df, period=20):
    """Gator Oscillator — разница между BB width и Keltner width."""
    mid = df['close'].rolling(period).mean()
    std = df['close'].rolling(period).std()
    bb_upper = mid + 2 * std
    bb_lower = mid - 2 * std
    bb_width = bb_upper - bb_lower

    atr = df['high'].rolling(period).max() - df['low'].rolling(period).min()
    kelt_width = 2 * atr

    gator = bb_width - kelt_width

    k = np.zeros(len(df))
    k[gator > gator.rolling(3).mean().shift(1)] = 1   # расширение
    k[gator < gator.rolling(3).mean().shift(1)] = -1  # сужение

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
    df = calc_osc_er_gator(df, int(param_key))
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
