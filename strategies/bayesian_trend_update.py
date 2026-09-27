"""Стратегия Bayesian trend update — вход при P(тренд) > 0.65, выход при P < 0.5."""
import numpy as np
import pandas as pd


def calc_bayesian_trend(df, window, prior=0.5, p_entry=0.65, p_exit=0.5):
    """
    Добавляет колонку 'p_trend' с вероятностью тренда через байесовское обновление.
    
    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        prior: априорная вероятность тренда
        p_entry: порог вероятности для входа
        p_exit: порог вероятности для выхода
    
    Returns:
        DataFrame с колонкой 'p_trend'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)
    
    p_trend_values = []
    p_trend = prior
    
    for i in range(len(df)):
        if i < window:
            p_trend_values.append(p_trend)
        else:
            window_returns = returns.iloc[i - window:i]
            # Вероятность роста в окне
            up_ratio = (window_returns > 0).sum() / len(window_returns)
            
            # Байесовское обновление
            # P(тренд|данные) = P(данные|тренд) * P(тренд) / P(данные)
            likelihood_up = up_ratio
            likelihood_down = 1 - up_ratio
            
            # Новая вероятность
            p_trend = (likelihood_up * p_trend) / \
                      (likelihood_up * p_trend + likelihood_down * (1 - p_trend))
            
            # Ограничиваем диапазон
            p_trend = np.clip(p_trend, 0.01, 0.99)
            p_trend_values.append(p_trend)
    
    df['p_trend'] = p_trend_values
    return df


def check_entry(prev_p, curr_p, p_entry):
    """
    Вход при росте вероятности тренда.
    
    Returns:
        'long', 'short' или None
    """
    if prev_p <= p_entry and curr_p > p_entry:
        return 'long'
    if prev_p >= (1 - p_entry) and curr_p < (1 - p_entry):
        return 'short'
    return None


def check_exit(prev_p, curr_p, p_exit, direction):
    """
    Выход при падении вероятности тренда.
    
    Args:
        direction: 'long' или 'short'
    
    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_p <= p_exit
    else:
        return curr_p >= (1 - p_exit)


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, window, prior, p_entry, p_exit, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Bayesian trend update.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_bayesian_trend(df, window, prior, p_entry, p_exit)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_p = df['p_trend'].iloc[i - 1]
        curr_p = df['p_trend'].iloc[i]
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
