"""Стратегия Skewness extreme — вход при Skewness < -1 или > 1, выход при |Skewness| < 0.3."""
import numpy as np
import pandas as pd


def calc_skewness(df, window, skew_entry=1.0, skew_exit=0.3):
    """
    Добавляет колонку 'skewness' с коэффициентом асимметии.
    
    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        skew_entry: порог Skewness для входа
        skew_exit: порог Skewness для выхода
    
    Returns:
        DataFrame с колонкой 'skewness'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)
    
    skew_values = []
    for i in range(len(df)):
        if i < window:
            skew_values.append(0)
        else:
            window_returns = returns.iloc[i - window:i]
            n = len(window_returns)
            mean = window_returns.mean()
            std = window_returns.std()
            
            if std == 0 or n < 3:
                skew_values.append(0)
            else:
                # Skewness = E[(X-μ)³] / σ³
                skew = ((window_returns - mean) ** 3).sum() / (n * std ** 3)
                skew_values.append(skew)
    
    df['skewness'] = skew_values
    return df


def check_entry(prev_skew, curr_skew, skew_entry, skew_exit):
    """
    Вход при экстремальной асимметии.
    
    Returns:
        'long' (отрицательная skewness), 'short' (положительная) или None
    """
    if prev_skew >= -skew_entry and curr_skew < -skew_entry:
        return 'long'
    if prev_skew <= skew_entry and curr_skew > skew_entry:
        return 'short'
    return None


def check_exit(prev_skew, curr_skew, skew_exit, direction):
    """
    Выход при возврате асимметии к нулю.
    
    Args:
        direction: 'long' или 'short'
    
    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_skew >= -skew_exit
    else:
        return curr_skew <= skew_exit


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, window, skew_entry, skew_exit, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Skewness extreme.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_skewness(df, window, skew_entry, skew_exit)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_skew = df['skewness'].iloc[i - 1]
        curr_skew = df['skewness'].iloc[i]
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
                elif check_exit(prev_skew, curr_skew, skew_exit, 'long'):
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
                elif check_exit(prev_skew, curr_skew, skew_exit, 'short'):
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
            entry_dir = check_entry(prev_skew, curr_skew, skew_entry, skew_exit)
            if entry_dir == 'long':
                entry = curr_close - spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close + spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
