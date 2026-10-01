"""Стратегия Kurtosis spike — вход при Kurtosis > 5 и последний бар > 1σ с направлением.

Kurtosis (эксцесс) показывает "тяжесть хвостов" распределения — высокий эксцесс
означает частые резкие движения. Но сам по себе Kurtosis НЕ даёт направления!

Направление задаётся знаком последнего возврата (current_return).

Вход: Kurtosis > 5 + |sigma| > 1 + current_return > 0 → LONG
      Kurtosis > 5 + |sigma| > 1 + current_return < 0 → SHORT
Выход: Kurtosis < 3 (экстремальность прошла)
"""
import numpy as np
import pandas as pd


def calc_kurtosis(df, window, kurt_entry=5.0, kurt_exit=3.0, sigma_mult=1.0):
    """
    Добавляет колонки 'kurtosis', 'sigma' и 'current_return' для определения направления.
    
    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        kurt_entry: порог Kurtosis для входа
        kurt_exit: порог Kurtosis для выхода
        sigma_mult: множитель стандартного отклонения
    
    Returns:
        DataFrame с колонками 'kurtosis', 'sigma', 'current_return', 'trend_up', 'trend_down'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)
    df['current_return'] = returns
    
    kurt_values = []
    sigma_values = []
    
    for i in range(len(df)):
        if i < window:
            kurt_values.append(0)
            sigma_values.append(0)
        else:
            window_returns = returns.iloc[i - window:i]
            n = len(window_returns)
            mean = window_returns.mean()
            std = window_returns.std()
            
            if std == 0 or n < 4:
                kurt_values.append(0)
                sigma_values.append(0)
            else:
                # Kurtosis = E[(X-μ)^4] / σ^4 - 3
                kurt = ((window_returns - mean) ** 4).sum() / (n * std ** 4) - 3
                kurt_values.append(kurt)
                
                # Текущее отклонение в сигмах (АБСОЛЮТНОЕ значение)
                current_return = returns.iloc[i]
                sigma = abs(current_return - mean) / std if std > 0 else 0
                sigma_values.append(sigma)
    
    df['kurtosis'] = kurt_values
    df['sigma'] = sigma_values
    
    # Направление по знаку current_return (текущий возврат)
    df['trend_up'] = (df['kurtosis'] > kurt_entry) & (df['sigma'] > sigma_mult) & (df['current_return'] > 0)
    df['trend_down'] = (df['kurtosis'] > kurt_entry) & (df['sigma'] > sigma_mult) & (df['current_return'] < 0)
    return df


def check_entry(prev_up, prev_down, curr_up, curr_down):
    """
    Вход при высоком эксцессе и большом последнем баре с направлением.
    
    Returns:
        'long' — экстремальное восходящее движение, 'short' — нисходящее, None — иначе
    """
    if curr_up and not prev_up:
        return 'long'
    if curr_down and not prev_down:
        return 'short'
    return None


def check_exit(prev_up, prev_down, curr_up, curr_down, direction):
    """
    Выход при падении эксцесса.
    
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


def backtest(df, window, kurt_entry, kurt_exit, sigma_mult, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Kurtosis spike.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_kurtosis(df, window, kurt_entry, kurt_exit, sigma_mult)
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
