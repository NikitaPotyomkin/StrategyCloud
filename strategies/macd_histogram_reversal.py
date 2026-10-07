"""Стратегия MACD histogram reversal — вход при развороте гистограммы от нуля."""
import numpy as np
import pandas as pd


def calc_macd_histogram(df, fast=12, slow=26, signal=9):
    """
    Добавляет колонку 'macd_hist' с гистограммой MACD и сигналом.
    
    Args:
        df: DataFrame с OHLCV
        fast: быстрый период EMA
        slow: медленный период EMA
        signal: период для сигнальной линии
    
    Returns:
        DataFrame с колонками 'macd', 'signal_line', 'macd_hist', 'macd_hist_signal'
    """
    df = df.copy()
    
    # Расчёт EMA
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    
    # MACD line
    df['macd'] = ema_fast - ema_slow
    
    # Signal line
    df['signal_line'] = df['macd'].ewm(span=signal, adjust=False).mean()
    
    # Гистограмма MACD
    df['macd_hist'] = df['macd'] - df['signal_line']
    
    # Сигнал: гистограмма положительная → long, отрицательная → short
    df['macd_hist_signal'] = 0
    df.loc[df['macd_hist'] > 0, 'macd_hist_signal'] = 1
    df.loc[df['macd_hist'] < 0, 'macd_hist_signal'] = -1
    
    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при развороте гистограммы MACD.
    
    Returns:
        'long', 'short' или None
    """
    # Long: был нейтральный или short-сигнал, теперь гистограмма положительная
    if prev_signal != 1 and curr_signal == 1:
        return 'long'
    # Short: был нейтральный или long-сигнал, теперь гистограмма отрицательная
    if prev_signal != -1 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при развороте гистограммы в противоположную сторону.
    
    Args:
        direction: 'long' или 'short'
    
    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_signal <= 0
    else:
        return curr_signal >= 0


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, fast, slow, signal, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с MACD histogram reversal.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_macd_histogram(df, fast, slow, signal)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['macd_hist_signal'].iloc[i - 1]
        curr_signal = df['macd_hist_signal'].iloc[i]
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
                elif check_exit(prev_signal, curr_signal, 'long'):
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
                elif check_exit(prev_signal, curr_signal, 'short'):
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
            entry_dir = check_entry(prev_signal, curr_signal)
            if entry_dir == 'long':
                entry = curr_close - spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close + spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
