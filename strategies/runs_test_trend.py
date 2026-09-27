"""Стратегия Runs Test trend — вход при Z-stat > 1.96 (тренд), выход при Z < 0."""
import numpy as np
import pandas as pd


def calc_runs_test(df, window, z_threshold=1.96):
    """
    Добавляет колонку 'z_stat' со Z-статистикой теста серий.
    
    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        z_threshold: порог Z для входа
    
    Returns:
        DataFrame с колонкой 'z_stat'
    """
    df = df.copy()
    z_values = []
    
    for i in range(len(df)):
        if i < window:
            z_values.append(0)
        else:
            x = df['close'].iloc[i - window:i]
            # Бинаризация: 1 если рост, 0 если падение
            signs = (x > x.shift(1)).astype(int).dropna()
            n = len(signs)
            
            if n < 10:
                z_values.append(0)
                continue
            
            # Количество серий
            runs = 1
            for j in range(1, n):
                if signs.iloc[j] != signs.iloc[j - 1]:
                    runs += 1
            
            # n1 и n2
            n1 = signs.sum()
            n2 = n - n1
            
            if n1 == 0 or n2 == 0:
                z_values.append(0)
                continue
            
            # Ожидаемое количество серий и дисперсия
            expected = (2 * n1 * n2) / (n1 + n2) + 1
            variance = (2 * n1 * n2 * (2 * n1 * n2 - n1 - n2)) / \
                       ((n1 + n2) ** 2 * (n1 + n2 - 1))
            
            if variance == 0:
                z_values.append(0)
            else:
                z = (runs - expected) / np.sqrt(variance)
                z_values.append(z)
    
    df['z_stat'] = z_values
    return df


def check_entry(prev_z, curr_z, z_threshold):
    """
    Вход при превышении Z-порога.
    
    Returns:
        'long', 'short' или None
    """
    if prev_z <= z_threshold and curr_z > z_threshold:
        return 'long'
    if prev_z >= -z_threshold and curr_z < -z_threshold:
        return 'short'
    return None


def check_exit(prev_z, curr_z, direction):
    """
    Выход при возврате Z к нулю.
    
    Args:
        direction: 'long' или 'short'
    
    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_z <= 0
    else:
        return curr_z >= 0


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, window, z_threshold, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Runs Test trend.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_runs_test(df, window, z_threshold)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_z = df['z_stat'].iloc[i - 1]
        curr_z = df['z_stat'].iloc[i]
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
                elif check_exit(prev_z, curr_z, 'long'):
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
                elif check_exit(prev_z, curr_z, 'short'):
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
            entry_dir = check_entry(prev_z, curr_z, z_threshold)
            if entry_dir == 'long':
                entry = curr_close - spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close + spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
