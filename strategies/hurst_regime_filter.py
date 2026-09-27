"""Стратегия Hurst regime filter — вход при H > 0.6 (тренд), выход при H < 0.5."""
import numpy as np
import pandas as pd


def calc_hurst(df, window, h_threshold=0.6, h_exit=0.5):
    """
    Добавляет колонку 'hurst' с показателем Хёрста скользящим окном.
    
    Args:
        df: DataFrame с OHLCV
        window: размер скользящего окна
        h_threshold: порог H для входа в тренд
        h_exit: порог H для выхода из тренда
    
    Returns:
        DataFrame с колонкой 'hurst'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)
    
    hurst_values = []
    for i in range(len(df)):
        if i < window:
            hurst_values.append(0.5)
        else:
            x = returns.iloc[i - window:i]
            # Расчёт H через R/S анализ
            mean = x.mean()
            deviations = x - mean
            cumulative = deviations.cumsum()
            range_rs = cumulative.max() - cumulative.min()
            std = x.std()
            
            if std == 0 or range_rs == 0:
                hurst_values.append(0.5)
            else:
                # H = log(R/S) / log(n)
                n = len(x)
                rs = range_rs / std
                if rs > 0 and n > 1:
                    h = np.log(rs) / np.log(n)
                    hurst_values.append(h)
                else:
                    hurst_values.append(0.5)
    
    df['hurst'] = hurst_values
    df['trend_up'] = df['hurst'] > h_threshold
    df['trend_down'] = df['hurst'] < h_exit
    return df


def check_entry(prev_trend, curr_trend):
    """
    Вход при смене тренда.
    
    Returns:
        'long', 'short' или None
    """
    if not prev_trend and curr_trend:
        return 'long'
    if prev_trend and not curr_trend:
        return 'short'
    return None


def check_exit(prev_trend, curr_trend, direction):
    """
    Выход при смене тренда.
    
    Args:
        direction: 'long' или 'short'
    
    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return not curr_trend
    else:
        return curr_trend


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, window, h_threshold, h_exit, sl_points, tp_points, point,
             tick_value, tick_size, vol_period=50, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Hurst regime filter.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_hurst(df, window, h_threshold, h_exit)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_trend = df['trend_up'].iloc[i - 1] if df['trend_up'].iloc[i - 1] else df['trend_down'].iloc[i - 1]
        curr_trend = df['trend_up'].iloc[i] if df['trend_up'].iloc[i] else df['trend_down'].iloc[i]
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
                elif check_exit(prev_trend, curr_trend, 'long'):
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
                elif check_exit(prev_trend, curr_trend, 'short'):
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
            entry_dir = check_entry(prev_trend, curr_trend)
            if entry_dir == 'long':
                entry = curr_close + spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close - spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
