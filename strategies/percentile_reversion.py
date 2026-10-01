"""Стратегия Percentile reversion — вход в 5-м или 95-м перцентиле, выход к 50-му.

Percentile показывает позицию цены в распределении за окно.
- Percentile > 95 → цена выше 95% предыдущих значений (перекупленность)
- Percentile < 5 → цена ниже 5% предыдущих значений (перепроданность)

Вход LONG: цена была в 95-м перцентиле (высокая), теперь падает (< 95)
Вход SHORT: цена была в 5-м перцентиле (низкая), теперь растёт (> 5)

Это mean-reversion: ожидаем возврат к средней.
"""
import numpy as np
import pandas as pd


def calc_percentile(df, lookback, low_pct=5, high_pct=95, mid_pct=50):
    """
    Добавляет колонку 'percentile' с позицией цены в распределении.
    
    Args:
        df: DataFrame с OHLCV
        lookback: размер окна для расчёта перцентиля
        low_pct: нижний порог перцентиля
        high_pct: верхний порог перцентиля
        mid_pct: порог возврата (середина)
    
    Returns:
        DataFrame с колонкой 'percentile'
    """
    df = df.copy()
    percentiles = []
    
    for i in range(len(df)):
        if i < lookback:
            percentiles.append(50)
        else:
            window = df['close'].iloc[i - lookback:i]
            current = df['close'].iloc[i]
            # Процент значений в окне меньше текущего
            pct = (window < current).sum() / len(window) * 100
            percentiles.append(pct)
    
    df['percentile'] = percentiles
    return df


def check_entry(prev_pct, curr_pct, low_pct, high_pct):
    """
    Вход при экстремальном перцентиле (mean-reversion).
    
    Returns:
        'long' (цена была внизу, теперь растёт), 'short' (цена была вверху, теперь падает) или None
    """
    if prev_pct >= high_pct and curr_pct < high_pct:
        return 'short'  # Цена была > 95-го перцентиля (очень высокая), теперь падает
    if prev_pct <= low_pct and curr_pct > low_pct:
        return 'long'  # Цена была < 5-го перцентиля (очень низкая), теперь растёт
    return None


def check_exit(prev_pct, curr_pct, mid_pct, direction):
    """
    Выход при возврате к середине.
    
    Args:
        direction: 'long' или 'short'
    
    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_pct >= mid_pct
    else:
        return curr_pct <= mid_pct


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, lookback, low_pct, high_pct, mid_pct, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Percentile reversion.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_percentile(df, lookback, low_pct, high_pct, mid_pct)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_pct = df['percentile'].iloc[i - 1]
        curr_pct = df['percentile'].iloc[i]
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
                elif check_exit(prev_pct, curr_pct, mid_pct, 'long'):
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
                elif check_exit(prev_pct, curr_pct, mid_pct, 'short'):
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
            entry_dir = check_entry(prev_pct, curr_pct, low_pct, high_pct)
            if entry_dir == 'long':
                entry = curr_close - spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close + spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
