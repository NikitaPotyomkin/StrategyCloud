"""Стратегия Bayesian trend update — вход при P(тренд) > 0.65 И направлении mean_ret.

Байесовское обновление оценивает ВЕРОЯТНОСТЬ тренда, но НЕ его направление.
Направление задаётся mean_ret (средний возврат за окно).

Вход: P(тренд) > 0.65 + mean_ret > 0 → LONG
      P(тренд) > 0.65 + mean_ret < 0 → SHORT
Выход: P(тренд) < 0.5 (вероятность тренда потеряна)
"""
import numpy as np
import pandas as pd


def calc_bayesian_trend(df, window, prior=0.5, p_entry=0.65, p_exit=0.5):
    """
    Добавляет колонки 'p_trend' и 'mean_ret' для определения направления.
    
    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        prior: априорная вероятность тренда
        p_entry: порог вероятности для входа
        p_exit: порог вероятности для выхода
    
    Returns:
        DataFrame с колонками 'p_trend', 'mean_ret', 'trend_up', 'trend_down'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)
    df['mean_ret'] = returns.rolling(window, min_periods=1).mean()
    
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
    
    # Направление по mean_ret (средний возврат за окно)
    df['trend_up'] = (df['p_trend'] > p_entry) & (df['mean_ret'] > 0)
    df['trend_down'] = (df['p_trend'] > p_entry) & (df['mean_ret'] < 0)
    return df


def check_entry(prev_up, prev_down, curr_up, curr_down):
    """
    Вход при росте вероятности тренда с направлением.
    
    Returns:
        'long' — появился сильный восходящий тренд, 'short' — нисходящий, None — иначе
    """
    if curr_up and not prev_up:
        return 'long'
    if curr_down and not prev_down:
        return 'short'
    return None


def check_exit(prev_up, prev_down, curr_up, curr_down, direction):
    """
    Выход при падении вероятности тренда.
    
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
