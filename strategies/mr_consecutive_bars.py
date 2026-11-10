"""Mean Reversion: Consecutive Bars (H1).

Idea: 0896 mr_consecutive_bars
Вход: 6 баров одного направления
Выход: 3 бара против
Отличие: Серия однонаправленных баров = истощение движения
"""
import numpy as np
import pandas as pd


def calc_mr_consecutive_bars(df, period=6):
    """6+ баров подряд одного знака."""
    ret = df['close'] - df['open']
    sign = np.sign(ret)

    # (right) считаем длину серии
    streak = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        if sign.iloc[i] == sign.iloc[i-1] and sign.iloc[i] != 0:
            streak.iloc[i] = streak.iloc[i-1] + 1
        else:
            streak.iloc[i] = 1

    k = np.zeros(len(df))
    k[streak > period] = 1   # серия вверх
    k[streak < -period] = -1  # серия вниз

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
    df = calc_mr_consecutive_bars(df, int(param_key))
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
