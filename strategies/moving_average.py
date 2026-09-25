"""Стратегия Moving Average — вход/выход по пересечению цены с MA."""
import numpy as np
import pandas as pd


def calc_moving_average(df, period):
    """Добавляет колонку 'ma' в копию DataFrame."""
    df = df.copy()
    df['ma'] = df['close'].rolling(period, min_periods=1).mean()
    return df


def check_entry(prev_ma, prev_price, curr_ma, curr_price):
    """
    Вход по пересечению цены с MA.
    """
    # Цена была ниже MA, стала выше → long
    if prev_price <= prev_ma and curr_price > curr_ma:
        return 'long'
    # Цена была выше MA, стала ниже → short
    if prev_price >= prev_ma and curr_price < curr_ma:
        return 'short'
    return None


def check_exit(prev_ma, prev_price, curr_ma, curr_price, direction):
    """
    Выход при пересечении цены с MA в обратную сторону.
    """
    if direction == 'long':
        # Цена была выше MA, стала ниже → выход из long
        return prev_price > prev_ma and curr_price < curr_ma
    else:
        # Цена была ниже MA, стала выше → выход из short
        return prev_price < prev_ma and curr_price > curr_ma


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, period, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с учётом Moving Average.
    Возвращает (profit, n_trades, trade_profits).
    """
    df = calc_moving_average(df, period)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_ma = df['ma'].iloc[i - 1]
        curr_ma = df['ma'].iloc[i]
        prev_close = df['close'].iloc[i - 1]
        curr_close = df['close'].iloc[i]
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]

        # ── Проверка выхода ──
        if position:
            exited = False
            p = 0.0
            d = position['direction']

            if d == 'long':
                if current_low <= position['sl']:
                    p = _profit(position['entry'], position['sl'],
                                tick_value, tick_size, sim_lot, 'long')
                    exited = True
                elif current_high >= position['tp']:
                    p = _profit(position['entry'], position['tp'],
                                tick_value, tick_size, sim_lot, 'long')
                    exited = True
                elif check_exit(prev_ma, prev_close, curr_ma, curr_close, 'long'):
                    p = _profit(position['entry'], curr_close,
                                tick_value, tick_size, sim_lot, 'long')
                    exited = True
            else:
                if current_high >= position['sl']:
                    p = _profit(position['entry'], position['sl'],
                                tick_value, tick_size, sim_lot, 'short')
                    exited = True
                elif current_low <= position['tp']:
                    p = _profit(position['entry'], position['tp'],
                                tick_value, tick_size, sim_lot, 'short')
                    exited = True
                elif check_exit(prev_ma, prev_close, curr_ma, curr_close, 'short'):
                    p = _profit(position['entry'], curr_close,
                                tick_value, tick_size, sim_lot, 'short')
                    exited = True

            if exited:
                p -= (spread / tick_size) * tick_value * sim_lot
                profit += p
                n_trades += 1
                trade_profits.append(p)
                position = None

        # ── Проверка входа ──
        if position is None:
            entry_dir = check_entry(prev_ma, prev_close, curr_ma, curr_close)
            if entry_dir == 'long':
                entry = curr_close + spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close - spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
