"""Стратегия Cointegration pairs — вход при отклонении спреда > 2σ, выход при возврате."""
import numpy as np
import pandas as pd


def calc_cointegration(df, window, z_entry=2.0, z_exit=0.0):
    """
    Добавляет колонку 'spread_z' с Z-скор спреда.
    
    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта спреда
        z_entry: порог Z для входа
        z_exit: порог Z для выхода
    
    Returns:
        DataFrame с колонкой 'spread_z'
    """
    df = df.copy()
    z_values = []
    
    for i in range(len(df)):
        if i < window:
            z_values.append(0)
        else:
            window_data = df['close'].iloc[i - window:i]
            mean = window_data.mean()
            std = window_data.std()
            
            if std == 0:
                z_values.append(0)
            else:
                current = df['close'].iloc[i]
                z = (current - mean) / std
                z_values.append(z)
    
    df['spread_z'] = z_values
    return df


def check_entry(prev_z, curr_z, z_entry):
    """
    Вход при отклонении спреда из нейтральной зоны.
    
    Returns:
        'long', 'short' или None
    """
    # Short: из нейтральной зоны (> -z_entry и < z_entry) вверх выше z_entry
    if prev_z >= -z_entry and prev_z <= z_entry and curr_z > z_entry:
        return 'short'
    # Long: из нейтральной зоны вниз ниже -z_entry
    if prev_z >= -z_entry and prev_z <= z_entry and curr_z < -z_entry:
        return 'long'
    return None


def check_exit(prev_z, curr_z, z_exit, direction):
    """
    Выход при возврате спреда к нулю.
    
    Args:
        direction: 'long' или 'short'
    
    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_z >= z_exit
    else:
        return curr_z <= z_exit


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, window, z_entry, z_exit, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Cointegration pairs.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_cointegration(df, window, z_entry, z_exit)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_z = df['spread_z'].iloc[i - 1]
        curr_z = df['spread_z'].iloc[i]
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
                elif check_exit(prev_z, curr_z, z_exit, 'long'):
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
                elif check_exit(prev_z, curr_z, z_exit, 'short'):
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
            entry_dir = check_entry(prev_z, curr_z, z_entry)
            if entry_dir == 'long':
                entry = curr_close - spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close + spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
