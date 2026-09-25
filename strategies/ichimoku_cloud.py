"""Стратегия Ichimoku Cloud.

Вход: цена пробивает облако в направлении тренда.
Выход: разворот облака (цена возвращается внутрь/за облако).
"""
import numpy as np
import pandas as pd


def calc_ichimoku(df, tenkan=9, kijun=26, senkou_b=52, displacement=26):
    """Добавляет колонку 'signal' на основе Ichimoku Cloud."""
    df = df.copy()

    # Tenkan-sen
    low_9 = df['low'].rolling(tenkan, min_periods=1).min()
    high_9 = df['high'].rolling(tenkan, min_periods=1).max()
    df['tenkan'] = (low_9 + high_9) / 2

    # Kijun-sen
    low_26 = df['low'].rolling(kijun, min_periods=1).min()
    high_26 = df['high'].rolling(kijun, min_periods=1).max()
    df['kijun'] = (low_26 + high_26) / 2

    # Senkou Span A
    df['senkou_a'] = ((df['tenkan'] + df['kijun']) / 2).shift(displacement)

    # Senkou Span B
    low_52 = df['low'].rolling(senkou_b, min_periods=1).min()
    high_52 = df['high'].rolling(senkou_b, min_periods=1).max()
    df['senkou_b'] = ((low_52 + high_52) / 2).shift(displacement)

    # Облако
    df['cloud_top'] = df[['senkou_a', 'senkou_b']].max(axis=1)
    df['cloud_bottom'] = df[['senkou_a', 'senkou_b']].min(axis=1)

    # Сигнал: пробой облака
    df['signal'] = 0
    long_cond = (df['close'] > df['cloud_top']) & \
                (df['close'].shift(1) <= df['cloud_top'].shift(1))
    short_cond = (df['close'] < df['cloud_bottom']) & \
                 (df['close'].shift(1) >= df['cloud_bottom'].shift(1))
    df.loc[long_cond, 'signal'] = 1
    df.loc[short_cond, 'signal'] = -1

    return df


def check_entry_ichimoku(prev_signal, curr_signal):
    """Вход по смене сигнала."""
    if prev_signal == 0 and curr_signal == 1:
        return 'long'
    if prev_signal == 0 and curr_signal == -1:
        return 'short'
    return None


def check_exit_ichimoku(prev_signal, curr_signal, direction):
    """Выход при развороте сигнала."""
    if direction == 'long':
        return curr_signal == -1
    return curr_signal == 1


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest_ichimoku(df, tenkan, kijun, senkou_b, displacement,
                      sl_points, tp_points, point, tick_value, tick_size,
                      sim_lot=0.01, spread_points=0):
    """Симуляция сделок на истории с Ichimoku Cloud.
    
    Возвращает (profit, n_trades, trade_profits).
    """
    df = calc_ichimoku(df, tenkan, kijun, senkou_b, displacement)
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
                elif check_exit_ichimoku(prev_signal, curr_signal, 'long'):
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
                elif check_exit_ichimoku(prev_signal, curr_signal, 'short'):
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
            entry_dir = check_entry_ichimoku(prev_signal, curr_signal)
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
check_entry = check_entry_ichimoku
check_exit = check_exit_ichimoku
