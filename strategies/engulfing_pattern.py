"""Стратегия Engulfing Pattern — вход при бычьем/медвежьем поглощении."""
import numpy as np
import pandas as pd


def calc_engulfing(df):
    """
    Добавляет колонку 'engulfing_signal' с сигналами паттерна поглощения.
    
    Args:
        df: DataFrame с OHLCV
    
    Returns:
        DataFrame с колонкой 'engulfing_signal'
    """
    df = df.copy()
    df['engulfing_signal'] = 0
    
    for i in range(len(df)):
        if i == 0:
            continue
        
        prev_open = df['open'].iloc[i - 1]
        prev_close = df['close'].iloc[i - 1]
        curr_open = df['open'].iloc[i]
        curr_close = df['close'].iloc[i]
        
        # Размеры тел свечей
        prev_body = abs(prev_close - prev_open)
        curr_body = abs(curr_close - curr_open)
        
        detected_signal = 0
        
        # Бычье поглощение: предыдущая медвежья, текущая бычья, тело текущей больше тела предыдущей
        if prev_close < prev_open and curr_close > curr_open:
            if curr_open <= prev_close and curr_close >= prev_open:
                detected_signal = 1
        # Медвежье поглощение: предыдущая бычья, текущая медвежья, тело текущей больше тела предыдущей
        elif prev_close > prev_open and curr_close < curr_open:
            if curr_open >= prev_close and curr_close <= prev_open:
                detected_signal = -1
        
        df.loc[df.index[i], 'engulfing_signal'] = detected_signal
    
    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при появлении паттерна поглощения.
    
    Returns:
        'long', 'short' или None
    """
    # Long: был нейтральный или short-сигнал, теперь бычье поглощение
    if prev_signal != 1 and curr_signal == 1:
        return 'long'
    # Short: был нейтральный или long-сигнал, теперь медвежье поглощение
    if prev_signal != -1 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при появлении противоположного сигнала или нейтральной зоны.
    
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


def backtest(df, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Engulfing Pattern.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_engulfing(df)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['engulfing_signal'].iloc[i - 1]
        curr_signal = df['engulfing_signal'].iloc[i]
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
