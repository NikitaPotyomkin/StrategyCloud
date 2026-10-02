"""Стратегия VWAP Reversion — вход при отклонении от VWAP на N сигм, выход при возврате."""
import numpy as np
import pandas as pd


def calc_vwap(df, vol_period=20, std_mult=2.0):
    """
    Добавляет колонки 'vwap', 'vwap_upper', 'vwap_lower' с линиями VWAP канала.
    
    Args:
        df: DataFrame с OHLCV
        vol_period: период для расчёта скользящего объёма
        std_mult: множитель стандартного отклонения для каналов
    
    Returns:
        DataFrame с колонками 'vwap', 'vwap_upper', 'vwap_lower', 'vwap_signal'
    """
    df = df.copy()
    
    # Рассчитываем Typical Price
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    
    # Рассчитываем VWAP (cumulative)
    cumulative_vp = (typical_price * df['volume']).cumsum()
    cumulative_vol = df['volume'].cumsum()
    
    df['vwap'] = cumulative_vp / cumulative_vol
    
    # Скользящий VWAP для расчёта отклонений
    rolling_vp = (typical_price * df['volume']).rolling(vol_period).sum()
    rolling_vol = df['volume'].rolling(vol_period).sum()
    rolling_vwap = rolling_vp / rolling_vol
    
    # Стандартное отклонение от VWAP
    residuals = typical_price - rolling_vwap
    std = residuals.rolling(vol_period).std()
    
    df['vwap_upper'] = rolling_vwap + std_mult * std
    df['vwap_lower'] = rolling_vwap - std_mult * std
    
    # Сигнал: цена выше верхней границы → short, ниже нижней → long
    df['vwap_signal'] = 0
    df.loc[typical_price > df['vwap_upper'], 'vwap_signal'] = -1
    df.loc[typical_price < df['vwap_lower'], 'vwap_signal'] = 1
    
    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при уходе цены за пределы канала VWAP.
    
    Returns:
        'long', 'short' или None
    """
    # Long: был нейтральный или short-сигнал, теперь цена ниже нижней границы
    if prev_signal != 1 and curr_signal == 1:
        return 'long'
    # Short: был нейтральный или long-сигнал, теперь цена выше верхней границы
    if prev_signal != -1 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при возврате к VWAP.
    
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


def backtest(df, vol_period, std_mult, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с VWAP Reversion.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_vwap(df, vol_period, std_mult)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['vwap_signal'].iloc[i - 1]
        curr_signal = df['vwap_signal'].iloc[i]
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
