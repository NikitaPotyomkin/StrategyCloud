"""Стратегия EMA Crossover (9/21).

Вход: пересечение быстрой и медленной EMA.
Выход: обратное пересечение.
"""
import numpy as np
import pandas as pd


def calc_ema_crossover(df, ema_fast=9, ema_slow=21):
    """Добавляет колонку 'signal' на основе пересечения EMA."""
    df = df.copy()

    df['ema_fast'] = df['close'].ewm(span=ema_fast, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=ema_slow, adjust=False).mean()

    # Сигнал: пересечение EMA
    df['signal'] = 0
    long_cond = (df['ema_fast'] > df['ema_slow']) & \
                (df['ema_fast'].shift(1) <= df['ema_slow'].shift(1))
    short_cond = (df['ema_fast'] < df['ema_slow']) & \
                 (df['ema_fast'].shift(1) >= df['ema_slow'].shift(1))
    df.loc[long_cond, 'signal'] = 1
    df.loc[short_cond, 'signal'] = -1

    return df


def check_entry_ema_crossover(prev_signal, curr_signal):
    """Вход по смене сигнала."""
    if prev_signal == 0 and curr_signal == 1:
        return 'long'
    if prev_signal == 0 and curr_signal == -1:
        return 'short'
    return None


def check_exit_ema_crossover(prev_signal, curr_signal, direction):
    """Выход при развороте сигнала."""
    if direction == 'long':
        return curr_signal == -1
    return curr_signal == 1


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest_ema_crossover(df, ema_fast, ema_slow, sl_points, tp_points,
                           point, tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """Симуляция сделок на истории с EMA Crossover.
    
    Возвращает (profit, n_trades, trade_profits).
    """
    df = calc_ema_crossover(df, ema_fast, ema_slow)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['signal'].iloc[i - 1]
        curr_signal = df['signal'].iloc[i]
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
                elif check_exit_ema_crossover(prev_signal, curr_signal, 'long'):
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
                elif check_exit_ema_crossover(prev_signal, curr_signal, 'short'):
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
            entry_dir = check_entry_ema_crossover(prev_signal, curr_signal)
            if entry_dir == 'long':
                entry = curr_close + spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close - spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits


# Алиасы для совместимости с IDE-референсами
check_entry = check_entry_ema_crossover
check_exit = check_exit_ema_crossover
