"""Oscillator: RVI (Relative Volatility Index) (H1).

Idea: 0330 osc_rvi_hlc
Вход: RVI кросс сигнальной линии
Выход: обратный кросс
Отличие: Волатильность вверх/вниз вместо цены
"""
import numpy as np
import pandas as pd


def calc_osc_rvi_hlc(df, period=10):
    """Relative Volatility Index — аналог RSI для волатильности."""
    up_move = df['high'].diff()
    down_move = df['low'].diff()

    up_vol = up_move.where(up_move > 0, 0.0).abs()
    down_vol = down_move.where(down_move < 0, 0.0).abs()

    avg_up = up_vol.rolling(period).mean()
    avg_down = down_vol.rolling(period).mean()

    rvi = 100 * avg_up / (avg_up + avg_down + 1e-12)
    signal = rvi.rolling(3).mean()

    k = np.zeros(len(df))
    k[(rvi > signal) & (rvi.shift(1) <= signal.shift(1))] = 1
    k[(rvi < signal) & (rvi.shift(1) >= signal.shift(1))] = -1

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
    df = calc_osc_rvi_hlc(df, int(param_key))
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
