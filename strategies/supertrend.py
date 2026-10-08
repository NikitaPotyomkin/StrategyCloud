"""Стратегия SuperTrend — вход при пробое линии SuperTrend."""
import numpy as np
import pandas as pd


def calc_supertrend(df, period=10, multiplier=3.0):
    """
    Добавляет колонку 'supertrend' с индикатором SuperTrend и сигналом.
    
    Args:
        df: DataFrame с OHLCV
        period: период для расчёта ATR
        multiplier: множитель ATR (по умолчанию 3.0)
    
    Returns:
        DataFrame с колонками 'supertrend', 'supertrend_signal'
    """
    df = df.copy()
    
    # Typical Price
    tp = (df['high'] + df['low'] + df['close']) / 3
    
    # ATR (Average True Range)
    tr1 = df['high'] - df['low']
    tr2 = abs(df['high'] - df['close'].shift())
    tr3 = abs(df['low'] - df['close'].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    
    # Basic Upper and Lower Bands
    basic_upper = tp + (multiplier * atr)
    basic_lower = tp - (multiplier * atr)
    
    # Final Upper Band (сглаживание)
    final_upper = pd.Series(np.nan, index=df.index)
    final_lower = pd.Series(np.nan, index=df.index)
    supertrend = pd.Series(np.nan, index=df.index)
    
    for i in range(len(df)):
        if i == 0:
            final_upper.iloc[i] = basic_upper.iloc[i]
            final_lower.iloc[i] = basic_lower.iloc[i]
            supertrend.iloc[i] = basic_lower.iloc[i]
            continue
        
        # Если цена выше предыдущей верхней границы — обновляем
        if tp.iloc[i] > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        elif tp.iloc[i] < final_lower.iloc[i - 1]:
            final_upper.iloc[i] = final_lower.iloc[i - 1]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]
        
        # Если цена ниже предыдущей нижней границы — обновляем
        if tp.iloc[i] < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        elif tp.iloc[i] > final_upper.iloc[i - 1]:
            final_lower.iloc[i] = final_upper.iloc[i - 1]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]
        
        # Определяем направление SuperTrend
        if tp.iloc[i] <= final_upper.iloc[i]:
            supertrend.iloc[i] = final_upper.iloc[i]
        else:
            supertrend.iloc[i] = final_lower.iloc[i]
    
    df['supertrend'] = supertrend
    df['final_upper'] = final_upper
    df['final_lower'] = final_lower
    
    # Сигнал: цена выше Supertrend → LONG, цена ниже Supertrend → SHORT
    df['supertrend_signal'] = 0
    df.loc[df['close'] > df['supertrend'], 'supertrend_signal'] = 1
    df.loc[df['close'] < df['supertrend'], 'supertrend_signal'] = -1
    
    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при смене направления SuperTrend.
    
    Returns:
        'long', 'short' или None
    """
    # Long: был нейтральный или short-сигнал, теперь цена выше Supertrend
    if prev_signal != 1 and curr_signal == 1:
        return 'long'
    # Short: был нейтральный или long-сигнал, теперь цена ниже Supertrend
    if prev_signal != -1 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при смене направления SuperTrend.
    
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


def backtest(df, period, multiplier, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с SuperTrend.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_supertrend(df, period, multiplier)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['supertrend_signal'].iloc[i - 1]
        curr_signal = df['supertrend_signal'].iloc[i]
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
