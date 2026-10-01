"""Стратегия Runs Test trend — вход при Z-stat > 1.96 (тренд) И mean_ret > 0.

Runs test проверяет СТАТИСТИЧЕСКУЮ ЗНАЧИМОСТЬ тренда (мало серий = тренд).
Но сам по себе Z-stat НЕ даёт направления — нужно mean_ret.

Вход LONG: Z > 1.96 (тренд) + mean_ret > 0 (восходящий)
Вход SHORT: Z < -1.96 (тренд) + mean_ret < 0 (нисходящий)
Выход: Z < 0 (тренд потерялся)
"""
import numpy as np
import pandas as pd


def calc_runs_test(df, window, z_threshold=1.96):
    """
    Добавляет колонки 'z_stat' и 'mean_ret' для определения направления.
    
    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        z_threshold: порог Z для входа
    
    Returns:
        DataFrame с колонками 'z_stat', 'mean_ret', 'trend_up', 'trend_down'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)
    df['mean_ret'] = returns.rolling(window, min_periods=1).mean()
    
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
    
    # Направление по mean_ret (средний возврат за окно)
    df['trend_up'] = (df['z_stat'] > z_threshold) & (df['mean_ret'] > 0)
    df['trend_down'] = (df['z_stat'] < -z_threshold) & (df['mean_ret'] < 0)
    return df


def check_entry(prev_up, prev_down, curr_up, curr_down):
    """
    Вход при статистически значимом тренде с направлением.
    
    Returns:
        'long' — восходящий тренд, 'short' — нисходящий, None — иначе
    """
    if curr_up and not prev_up:
        return 'long'
    if curr_down and not prev_down:
        return 'short'
    return None


def check_exit(prev_up, prev_down, curr_up, curr_down, direction):
    """
    Выход при потере тренда.
    
    Args:
        direction: 'long' или 'short'
    
    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return not curr_up
    else:
        return not curr_down


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
        prev_up = df['trend_up'].iloc[i - 1]
        prev_down = df['trend_down'].iloc[i - 1]
        curr_up = df['trend_up'].iloc[i]
        curr_down = df['trend_down'].iloc[i]
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
                elif check_exit(prev_up, prev_down, curr_up, curr_down, 'long'):
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
                elif check_exit(prev_up, prev_down, curr_up, curr_down, 'short'):
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
            entry_dir = check_entry(prev_up, prev_down, curr_up, curr_down)
            if entry_dir == 'long':
                entry = curr_close - spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close + spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
