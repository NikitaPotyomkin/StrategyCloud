"""Стратегия Prev Daily Candle Direction — вход в направлении закрытия прошлой дневной свечи."""
import numpy as np
import pandas as pd


def calc_prev_daily_direction(df, hold_bars=12):
    """
    Добавляет колонку 'daily_direction' с направлением прошлой дневной свечи.
    
    Args:
        df: DataFrame с часовыми данными (H1)
        hold_bars: количество баров удержания позиции (по умолчанию 12 часовых)
    
    Returns:
        DataFrame с колонкой 'daily_direction', 'daily_signal'
    """
    df = df.copy()
    
    # Ресэмплим до дневных баров
    daily = df.resample('1D', label='left', closed='left').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    })
    
    # Направление дневной свечи
    daily['daily_direction'] = np.sign(daily['close'] - daily['open'])
    
    # Сигнал для каждого часа: направление предыдущего дня
    daily_signal = pd.Series(0, index=df.index)
    
    for i in range(1, len(daily)):
        direction = daily['daily_direction'].iloc[i - 1]
        if direction != 0:
            # Применяем сигнал на весь текущий день
            day_start = daily.index[i]
            day_end = day_start + pd.Timedelta(days=1)
            mask = (df.index >= day_start) & (df.index < day_end)
            daily_signal[mask] = direction
    
    df['daily_signal'] = daily_signal
    
    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при смене направления дневной свечи.
    
    Returns:
        'long', 'short' или None
    """
    # Long: был нейтральный или short-сигнал, теперь восходящий
    if prev_signal != 1 and curr_signal == 1:
        return 'long'
    # Short: был нейтральный или long-сигнал, теперь нисходящий
    if prev_signal != -1 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при смене направления дневной свечи.
    
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


def backtest(df, hold_bars, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Prev Daily Candle Direction.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_prev_daily_direction(df, hold_bars)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['daily_signal'].iloc[i - 1]
        curr_signal = df['daily_signal'].iloc[i]
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
