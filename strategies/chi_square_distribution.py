"""Стратегия Chi-square distribution — вход при p-value < 0.05, выход при p > 0.2."""
import numpy as np
import pandas as pd


def calc_chi_square(df, window, p_entry=0.05, p_exit=0.2):
    """
    Добавляет колонку 'chi2_pvalue' с p-value теста хи-квадрат.
    
    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        p_entry: порог p-value для входа
        p_exit: порог p-value для выхода
    
    Returns:
        DataFrame с колонкой 'chi2_pvalue'
    """
    df = df.copy()
    p_values = []
    
    for i in range(len(df)):
        if i < window:
            p_values.append(1.0)
        else:
            window_returns = df['close'].iloc[i - window:i].pct_change().dropna()
            
            if len(window_returns) < 5:
                p_values.append(1.0)
                continue
            
            # Разбиваем на группы: положительные и отрицательные
            positive = window_returns[window_returns > 0]
            negative = window_returns[window_returns < 0]
            
            n_pos = len(positive)
            n_neg = len(negative)
            n_total = len(window_returns)
            
            if n_total < 10 or n_pos == 0 or n_neg == 0:
                p_values.append(1.0)
                continue
            
            # Хи-квадрат тест на равенство долей
            expected_pos = n_total / 2
            expected_neg = n_total / 2
            
            chi2 = ((n_pos - expected_pos) ** 2 / expected_pos +
                    (n_neg - expected_neg) ** 2 / expected_neg)
            
            # p-value для 1 степени свободы
            from scipy.stats import chi2 as chi2_dist
            p_value = 1 - chi2_dist.cdf(chi2, 1)
            p_values.append(p_value)
    
    df['chi2_pvalue'] = p_values
    return df


def check_entry(prev_p, curr_p, p_entry):
    """
    Вход при низком p-value (статистическая значимость).
    
    Returns:
        'long', 'short' или None
    """
    if prev_p >= p_entry and curr_p < p_entry:
        return 'long'  # Или 'short' в зависимости от направления
    return None


def check_exit(prev_p, curr_p, p_exit, direction):
    """
    Выход при высоком p-value.
    
    Args:
        direction: 'long' или 'short'
    
    Returns:
        True если нужно выйти
    """
    return curr_p > p_exit


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, window, p_entry, p_exit, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Chi-square distribution.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    try:
        from scipy.stats import chi2 as chi2_dist
    except ImportError:
        # Если scipy нет, возвращаем нулевой результат
        return 0, 0, []
    
    df = calc_chi_square(df, window, p_entry, p_exit)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_p = df['chi2_pvalue'].iloc[i - 1]
        curr_p = df['chi2_pvalue'].iloc[i]
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
                elif check_exit(prev_p, curr_p, p_exit, 'long'):
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
                elif check_exit(prev_p, curr_p, p_exit, 'short'):
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
            entry_dir = check_entry(prev_p, curr_p, p_entry)
            if entry_dir == 'long':
                entry = curr_close - spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close + spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
