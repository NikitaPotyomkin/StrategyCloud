"""Oscillator: Pretty Good Oscillator (H1).

Idea: 0359 osc_pgo
Вход: PGO > 3 и растёт 3 бара
Выход: PGO < 0
Отличие: Отклонение цены от SMA, нормированное на среднюю цену
"""
import numpy as np
import pandas as pd


def calc_osc_pgo(df, period=14):
    """Pretty Good Oscillator от Джона Эллса."""
    sma = df['close'].rolling(period).mean()
    mad = df['close'].rolling(period).apply(lambda x: abs(x - x.mean()).mean())
    mad = mad.replace(0, np.nan).ffill()

    pgo = (df['close'] - sma) / (mad + 1e-12)

    # (right) PGO > 3 и растёт 3 бара подряд
    pgo_rising = (pgo > pgo.shift(1)) & (pgo.shift(1) > pgo.shift(2))
    k = np.zeros(len(df))
    k[(pgo > 3) & pgo_rising] = 1
    k[(pgo < -3) & (pgo < pgo.shift(1)) & (pgo.shift(1) < pgo.shift(2))] = -1

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
    df = calc_osc_pgo(df, int(param_key))
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
