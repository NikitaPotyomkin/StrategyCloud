"""Стратегия Morning/Evening Star — вход при разворотной паттерне из 3 свечей."""
import numpy as np
import pandas as pd


def calc_morning_evening_star(df, min_body_ratio=0.3):
    """
    Добавляет колонку 'star_signal' с сигналом разворотного паттерна Morning/Evening Star.
    
    Args:
        df: DataFrame с OHLCV
        min_body_ratio: минимальное отношение тела первой свечи к диапазону (по умолчанию 0.3)
    
    Returns:
        DataFrame с колонкой 'star_signal'
    """
    df = df.copy()
    
    # Расчёт параметров свечи
    df['body'] = abs(df['close'] - df['open'])
    df['range'] = df['high'] - df['low']
    df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
    df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']
    
    # Morning Star (бычий разворот):
    # 1. Первая свеча — длинная медвежья (close < open)
    # 2. Вторая свеча — маленькая (doji/spinning top), пробел от первой
    # 3. Третья свеча — длинная бычья (close > open), закрывается в тело первой
    
    # Evening Star (медвежий разворот):
    # 1. Первая свеча — длинная бычья (close > open)
    # 2. Вторая свеча — маленькая (doji/spinning top), пробел от первой
    # 3. Третья свеча — длинная медвежья (close < open), закрывается в тело первой
    
    df['star_signal'] = 0
    
    for i in range(2, len(df)):
        # Свеча 1 (прошлая-прошлая)
        c1 = df['close'].iloc[i - 2]
        o1 = df['open'].iloc[i - 2]
        body1 = df['body'].iloc[i - 2]
        range1 = df['range'].iloc[i - 2]
        
        # Свеча 2 (прошлая)
        c2 = df['close'].iloc[i - 1]
        o2 = df['open'].iloc[i - 1]
        body2 = df['body'].iloc[i - 1]
        range2 = df['range'].iloc[i - 1]
        
        # Свеча 3 (текущая)
        c3 = df['close'].iloc[i]
        o3 = df['open'].iloc[i]
        body3 = df['body'].iloc[i]
        range3 = df['range'].iloc[i]
        
        # Проверка Morning Star (бычий разворот)
        is_bearish1 = c1 < o1  # Первая медвежья
        is_doji2 = body2 < range2 * min_body_ratio  # Вторая маленькая
        is_bullish3_morning = c3 > o3  # Третья бычья
        
        # Проверка пробела между свечами 1 и 2
        gap_down = o2 < c1  # Вторая ниже первой
        
        # Третья закрывается в тело первой
        closes_in_body1_morning = c3 > o1
        
        # Третья свеча длинная
        long_third_morning = body3 > range3 * 0.6
        
        if (is_bearish1 and is_doji2 and is_bullish3_morning and 
            gap_down and closes_in_body1_morning and long_third_morning):
            df.loc[df.index[i], 'star_signal'] = 1
        
        # Проверка Evening Star (медвежий разворот) — уникальные переменные
        is_bullish1_evening = c1 > o1  # Первая бычья
        is_bearish3_evening = c3 < o3  # Третья медвежья
        
        # Проверка пробела между свечами 1 и 2
        gap_up = o2 > c1  # Вторая выше первой
        
        # Третья закрывается в тело первой
        closes_in_body1_evening = c3 < o1
        
        # Третья свеча длинная
        long_third_evening = body3 > range3 * 0.6
        
        if (is_bullish1_evening and is_doji2 and is_bearish3_evening and 
            gap_up and closes_in_body1_evening and long_third_evening):
            df.loc[df.index[i], 'star_signal'] = -1
    
    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при появлении разворотного паттерна Morning/Evening Star.
    
    Returns:
        'long', 'short' или None
    """
    # Long: был нейтральный или short-сигнал, теперь Morning Star (бычий разворот)
    if prev_signal != 1 and curr_signal == 1:
        return 'long'
    # Short: был нейтральный или long-сигнал, теперь Evening Star (медвежий разворот)
    if prev_signal != -1 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при появлении противоположного сигнала.
    
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


def backtest(df, min_body_ratio, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Morning/Evening Star.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_morning_evening_star(df, min_body_ratio)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['star_signal'].iloc[i - 1]
        curr_signal = df['star_signal'].iloc[i]
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
