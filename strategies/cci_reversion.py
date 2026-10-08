"""Стратегия CCI Reversion — вход при выходе CCI из зон экстремума (mean reversion)."""
import numpy as np
import pandas as pd


def calc_cci(df, period=14, threshold=100):
    """
    Добавляет колонку 'cci' с Commodity Channel Index и сигналом.
    
    Args:
        df: DataFrame с OHLCV
        period: период для расчёта CCI
        threshold: пороговое значение CCI (по умолчанию 100)
    
    Returns:
        DataFrame с колонками 'cci', 'cci_signal'
    """
    df = df.copy()
    
    # Typical Price
    tp = (df['high'] + df['low'] + df['close']) / 3
    
    # Mean Price
    mean_price = tp.rolling(period).mean()
    
    # Mean Deviation
    dev = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean())
    
    # CCI = (Typical Price - Mean Price) / (0.015 * Mean Deviation)
    # 0.015 — стандартный множитель для CCI
    df['cci'] = np.where(dev != 0,
                         (tp - mean_price) / (0.015 * dev),
                         0)
    
    # Сигнал: CCI < -threshold → LONG (перепроданность), CCI > threshold → SHORT (перекупленность)
    df['cci_signal'] = 0
    df.loc[df['cci'] < -threshold, 'cci_signal'] = 1
    df.loc[df['cci'] > threshold, 'cci_signal'] = -1
    
    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при выходе из экстремальной зоны CCI (mean reversion).
    
    Returns:
        'long', 'short' или None
    """
    # Long: был нейтральный или short-сигнал, теперь CCI < -threshold (перепроданность)
    if prev_signal != 1 and curr_signal == 1:
        return 'long'
    # Short: был нейтральный или long-сигнал, теперь CCI > threshold (перекупленность)
    if prev_signal != -1 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при возврате из экстремальной зоны в нейтральную.
    
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


def backtest(df, period, threshold, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с CCI Reversion.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_cci(df, period, threshold)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['cci_signal'].iloc[i - 1]
        curr_signal = df['cci_signal'].iloc[i]
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
