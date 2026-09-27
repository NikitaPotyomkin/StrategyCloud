"""Стратегия Linear Regression Channel — вход при выходе за пределы ±2σ, выход при возврате."""
import numpy as np
import pandas as pd


def calc_lr_channel(df, lr_period, sigma_mult=2.0):
    """
    Добавляет колонки 'lr_line', 'lr_upper', 'lr_lower' с линией регрессии и каналами.
    
    Args:
        df: DataFrame с OHLCV
        lr_period: период для линейной регрессии
        sigma_mult: множитель стандартного отклонения для каналов
    
    Returns:
        DataFrame с колонками 'lr_line', 'lr_upper', 'lr_lower', 'lr_signal'
    """
    df = df.copy()
    n = len(df)
    lr_line = []
    lr_upper = []
    lr_lower = []
    
    for i in range(n):
        if i < lr_period - 1:
            lr_line.append(df['close'].iloc[i])
            lr_upper.append(df['close'].iloc[i])
            lr_lower.append(df['close'].iloc[i])
        else:
            x = np.arange(lr_period)
            y = df['close'].iloc[i - lr_period + 1:i + 1].values
            
            # Линейная регрессия y = a + b*x
            x_mean = x.mean()
            y_mean = y.mean()
            num = ((x - x_mean) * (y - y_mean)).sum()
            den = ((x - x_mean) ** 2).sum()
            
            if den == 0:
                a = y_mean
                b = 0
            else:
                b = num / den
                a = y_mean - b * x_mean
            
            # Значение линии на последнем баре
            line_value = a + b * (lr_period - 1)
            lr_line.append(line_value)
            
            # Стандартное отклонение
            residuals = y - (a + b * x)
            std = residuals.std()
            
            lr_upper.append(line_value + sigma_mult * std)
            lr_lower.append(line_value - sigma_mult * std)
    
    df['lr_line'] = lr_line
    df['lr_upper'] = lr_upper
    df['lr_lower'] = lr_lower
    
    # Сигнал: цена выше верхней границы → short, ниже нижней → long
    df['lr_signal'] = 0
    df.loc[df['close'] > df['lr_upper'], 'lr_signal'] = -1
    df.loc[df['close'] < df['lr_lower'], 'lr_signal'] = 1
    
    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при появлении сигнала.
    
    Returns:
        'long', 'short' или None
    """
    if prev_signal == 0 and curr_signal == 1:
        return 'long'
    if prev_signal == 0 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при возврате к линии регрессии.
    
    Args:
        direction: 'long' или 'short'
    
    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_signal <= 0
    else:
        return curr_signal >= 0


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, lr_period, sigma_mult, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Linear Regression Channel.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_lr_channel(df, lr_period, sigma_mult)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['lr_signal'].iloc[i - 1]
        curr_signal = df['lr_signal'].iloc[i]
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
                elif check_exit(prev_signal, curr_signal, 'long'):
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
                elif check_exit(prev_signal, curr_signal, 'short'):
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
            entry_dir = check_entry(prev_signal, curr_signal)
            if entry_dir == 'long':
                entry = curr_close - spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close + spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
