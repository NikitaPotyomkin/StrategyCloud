"""Oscillator: Fisher Transform (H1).

Idea: 0321 osc_fisher_transform
Вход: Fisher > 1.5 и разворот сверху
Выход: Fisher < 0
Отличие: Экстремумы и развороты через трансформацию Фишера
"""
import numpy as np
import pandas as pd


def calc_osc_fisher_transform(df, period=10):
    """Fisher transform на медиане цены."""
    high_ = df['high'].rolling(period).max()
    low_ = df['low'].rolling(period).min()
    median = (high_ + low_) / 2.0

    # (right) clip для предотвращения log(0)
    v = 0.5 * ((df['close'] - low_) / (high_ - low_ + 1e-12) - 0.5)
    v = np.clip(v, -0.99, 0.99)

    fisher = pd.Series(0.0, index=df.index)
    for i in range(1, len(df)):
        fisher.iloc[i] = 0.5 * np.log((1 + v.iloc[i]) / (1 - v.iloc[i] + 1e-12)) + 0.5 * fisher.iloc[i-1]

    signal = fisher.shift(1)
    k = np.zeros(len(df))
    k[(fisher > 1.5) & (signal <= 1.5)] = 1    # разворот вниз
    k[(fisher < -1.5) & (signal >= -1.5)] = -1  # разворот вверх

    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Возвращает 'long' / 'short' / None для engine run_backtest
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
    df = calc_osc_fisher_transform(df, int(param_key))
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
