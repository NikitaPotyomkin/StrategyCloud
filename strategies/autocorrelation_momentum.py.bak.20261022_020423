"""Стратегия Autocorrelation momentum — вход при ACF(1) > порога, выход при падении."""
import numpy as np
import pandas as pd


def calc_autocorrelation(df, acf_lag, vol_period=20):
    """
    Добавляет колонку 'acf' с автокорреляцией лага 1.
    
    Args:
        df: DataFrame с OHLCV
        acf_lag: лаг для расчёта автокорреляции
        vol_period: период для расчёта объёма
    
    Returns:
        DataFrame с колонкой 'acf'
    """
    df = df.copy()
    returns = df['close'].pct_change()
    
    # Расчёт автокорреляции лага 1
    acf_values = []
    for i in range(len(df)):
        if i < acf_lag + 1:
            acf_values.append(0)
        else:
            x = returns.iloc[i - acf_lag:i + 1]
            mean_x = x.mean()
            num = ((x - mean_x) * (x.shift(acf_lag) - mean_x)).sum()
            den = ((x - mean_x) ** 2).sum()
            if den == 0:
                acf_values.append(0)
            else:
                acf_values.append(num / den)
    
    df['acf'] = acf_values
    return df


def check_entry(prev_acf, curr_acf, threshold):
    """
    Вход при росте автокорреляции выше порога.
    
    Returns:
        'long' или 'short' или None
    """
    # Рост ACF выше порога → продолжение тренда
    if prev_acf <= threshold and curr_acf > threshold:
        return 'long'
    # Падение ACF ниже порога → выход
    if prev_acf >= -threshold and curr_acf < -threshold:
        return 'short'
    return None


def check_exit(prev_acf, curr_acf, threshold, direction):
    """
    Выход при падении ACF ниже порога.
    
    Args:
        direction: 'long' или 'short'
    
    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_acf < threshold * 0.5
    else:
        return curr_acf > -threshold * 0.5


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, acf_lag, threshold, sl_points, tp_points, point,
             tick_value, tick_size, vol_period=20, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Autocorrelation momentum.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_autocorrelation(df, acf_lag, vol_period)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_acf = df['acf'].iloc[i - 1]
        curr_acf = df['acf'].iloc[i]
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
                elif check_exit(prev_acf, curr_acf, threshold, 'long'):
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
                elif check_exit(prev_acf, curr_acf, threshold, 'short'):
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
            entry_dir = check_entry(prev_acf, curr_acf, threshold)
            if entry_dir == 'long':
                entry = curr_close + spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close - spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
