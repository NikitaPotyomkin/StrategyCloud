import numpy as np
import pandas as pd

OVERSOLD = 20
OVERBOUGHT = 80
SLOWING = 3
D_PERIOD = 3


def calc_stochastic(df, k_period):
    """Добавляет колонки k и d в копию DataFrame."""
    low_min = df['low'].rolling(k_period, min_periods=1).min()
    high_max = df['high'].rolling(k_period, min_periods=1).max()
    k_raw = 100 * (df['close'] - low_min) / (high_max - low_min)
    k_raw = k_raw.replace([np.inf, -np.inf], np.nan).fillna(50)
    df = df.copy()
    df['k'] = k_raw.rolling(SLOWING, min_periods=1).mean()
    df['d'] = df['k'].rolling(D_PERIOD, min_periods=1).mean()
    return df


def check_entry(prev_k, last_k):
    if prev_k <= OVERSOLD and last_k > OVERSOLD:
        return 'long'
    if prev_k >= OVERBOUGHT and last_k < OVERBOUGHT:
        return 'short'
    return None


def check_exit(prev_k, last_k, direction):
    if direction == 'long':
        return prev_k >= OVERBOUGHT and last_k < OVERBOUGHT
    else:
        return prev_k <= OVERSOLD and last_k > OVERSOLD


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, k_period, sl_points, tp_points, point, tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """Симуляция сделок на истории H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    df = calc_stochastic(df, k_period)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []  # ← ДОБАВИТЬ ЭТО

    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i - 1]
        last_k = df['k'].iloc[i]
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]
        close = df['close'].iloc[i]

        # ── Проверка выхода ──
        if position:
            exited = False
            p = 0.0
            d = position['direction']

            if d == 'long':
                if low <= position['sl']:
                    p = _profit(position['entry'], position['sl'], tick_value, tick_size, sim_lot, 'long')
                    p -= (spread / tick_size) * tick_value * sim_lot
                    exited = True
                elif high >= position['tp']:
                    p = _profit(position['entry'], position['tp'], tick_value, tick_size, sim_lot, 'long')
                    p -= (spread / tick_size) * tick_value * sim_lot
                    exited = True
                elif check_exit(prev_k, last_k, 'long'):
                    p = _profit(position['entry'], close, tick_value, tick_size, sim_lot, 'long')
                    p -= (spread / tick_size) * tick_value * sim_lot
                    exited = True
            else:
                if high >= position['sl']:
                    p = _profit(position['entry'], position['sl'], tick_value, tick_size, sim_lot, 'short')
                    p -= (spread / tick_size) * tick_value * sim_lot
                    exited = True
                elif low <= position['tp']:
                    p = _profit(position['entry'], position['tp'], tick_value, tick_size, sim_lot, 'short')
                    p -= (spread / tick_size) * tick_value * sim_lot
                    exited = True
                elif check_exit(prev_k, last_k, 'short'):
                    p = _profit(position['entry'], close, tick_value, tick_size, sim_lot, 'short')
                    p -= (spread / tick_size) * tick_value * sim_lot
                    exited = True

            if exited:
                profit += p
                n_trades += 1
                trade_profits.append(p)  # ← ДОБАВИТЬ ЭТО
                position = None

        # ── Проверка входа ──
        if position is None:
            entry_dir = check_entry(prev_k, last_k)
            if entry_dir == 'long':
                entry = close + spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = close
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits

