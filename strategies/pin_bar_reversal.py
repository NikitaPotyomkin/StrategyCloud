"""Стратегия Pin Bar reversal — вход при паттерне Pin Bar с подтверждением."""
import numpy as np
import pandas as pd


def calc_pin_bar(df, body_ratio=0.3, confirmation=True):
    """
    Добавляет колонку 'pin_bar_signal' с сигналами паттерна Pin Bar.
    
    Args:
        df: DataFrame с OHLCV
        body_ratio: минимальное отношение тени к телу (по умолчанию 0.3)
        confirmation: использовать подтверждение следующего бара
    
    Returns:
        DataFrame с колонкой 'pin_bar_signal'
    """
    df = df.copy()
    df['pin_bar_signal'] = 0
    
    for i in range(len(df)):
        open_price = df['open'].iloc[i]
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]
        close = df['close'].iloc[i]
        
        # Размер свечи
        body = abs(close - open_price)
        range_size = high - low
        
        if range_size == 0:
            continue
        
        # Отношение тени к телу
        upper_shadow = high - max(open_price, close)
        lower_shadow = min(open_price, close) - low
        
        detected_signal = 0
        
        # Pin Bar с длинной нижней тенью (бычий)
        if lower_shadow > body_ratio * range_size and upper_shadow < body * 0.5:
            detected_signal = 1
        # Pin Bar с длинной верхней тенью (медвежий)
        elif upper_shadow > body_ratio * range_size and lower_shadow < body * 0.5:
            detected_signal = -1
        
        if detected_signal != 0:
            if confirmation and i < len(df) - 1:
                # Подтверждение: следующий бар закрывается выше/ниже Pin Bar
                next_close = df['close'].iloc[i + 1]
                next_high = df['high'].iloc[i + 1]
                next_low = df['low'].iloc[i + 1]
                
                if detected_signal == 1 and next_close > high:
                    df.loc[df.index[i], 'pin_bar_signal'] = 1
                elif detected_signal == -1 and next_close < low:
                    df.loc[df.index[i], 'pin_bar_signal'] = -1
            else:
                df.loc[df.index[i], 'pin_bar_signal'] = detected_signal
    
    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при появлении Pin Bar.
    
    Returns:
        'long', 'short' или None
    """
    # Long: был нейтральный или short-сигнал, теперь бычий Pin Bar
    if prev_signal != 1 and curr_signal == 1:
        return 'long'
    # Short: был нейтральный или long-сигнал, теперь медвежий Pin Bar
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


def backtest(df, body_ratio, confirmation, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Pin Bar reversal.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_pin_bar(df, body_ratio, confirmation)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['pin_bar_signal'].iloc[i - 1]
        curr_signal = df['pin_bar_signal'].iloc[i]
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
