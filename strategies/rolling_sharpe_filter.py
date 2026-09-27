"""Стратегия Rolling Sharpe filter — вход при Sharpe(N) > 0.5, выход при Sharpe < 0."""
import numpy as np
import pandas as pd


def calc_rolling_sharpe(df, window, sharpe_entry=0.5, sharpe_exit=0.0):
    """
    Добавляет колонку 'sharpe' с скользящим коэффициентом Шарпа.
    
    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        sharpe_entry: порог Sharpe для входа
        sharpe_exit: порог Sharpe для выхода
    
    Returns:
        DataFrame с колонкой 'sharpe'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)
    
    sharpe_values = []
    for i in range(len(df)):
        if i < window:
            sharpe_values.append(0)
        else:
            window_returns = returns.iloc[i - window:i]
            mean_ret = window_returns.mean()
            std_ret = window_returns.std()
            
            if std_ret == 0:
                sharpe_values.append(0)
            else:
                sharpe = mean_ret / std_ret * np.sqrt(252 * 24)  # Annualized
                sharpe_values.append(sharpe)
    
    df['sharpe'] = sharpe_values
    return df


def check_entry(prev_sharpe, curr_sharpe, sharpe_entry):
    """
    Вход при росте Sharpe выше порога.
    
    Returns:
        'long', 'short' или None
    """
    if prev_sharpe <= sharpe_entry and curr_sharpe > sharpe_entry:
        return 'long'
    if prev_sharpe >= -sharpe_entry and curr_sharpe < -sharpe_entry:
        return 'short'
    return None


def check_exit(prev_sharpe, curr_sharpe, sharpe_exit, direction):
    """
    Выход при падении Sharpe ниже порога.
    
    Args:
        direction: 'long' или 'short'
    
    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_sharpe <= sharpe_exit
    else:
        return curr_sharpe >= -sharpe_exit


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, window, sharpe_entry, sharpe_exit, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Rolling Sharpe filter.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_rolling_sharpe(df, window, sharpe_entry, sharpe_exit)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_sharpe = df['sharpe'].iloc[i - 1]
        curr_sharpe = df['sharpe'].iloc[i]
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
                elif check_exit(prev_sharpe, curr_sharpe, sharpe_exit, 'long'):
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
                elif check_exit(prev_sharpe, curr_sharpe, sharpe_exit, 'short'):
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
            entry_dir = check_entry(prev_sharpe, curr_sharpe, sharpe_entry)
            if entry_dir == 'long':
                entry = curr_close - spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close + spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
