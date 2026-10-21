"""Стратегия Z-score reversion — вход при отклонении от SMA > порога, выход при возврате."""
import numpy as np
import pandas as pd


def calc_zscore(df, sma_period, z_threshold, vol_period=20):
    """
    Добавляет колонки 'sma', 'std', 'zscore' в копию DataFrame.
    
    Args:
        df: DataFrame с OHLCV
        sma_period: период скользящей средней
        z_threshold: порог Z-score для входа
        vol_period: период для расчёта волатильности (для объёма)
    
    Returns:
        DataFrame с колонками 'sma', 'std', 'zscore', 'vol_signal'
    """
    df = df.copy()
    df['sma'] = df['close'].rolling(sma_period, min_periods=1).mean()
    df['std'] = df['close'].rolling(sma_period, min_periods=1).std()
    df['zscore'] = (df['close'] - df['sma']) / df['std'].replace(0, np.nan)
    df['zscore'] = df['zscore'].fillna(0)
    
    # Сигнал по объёму (для информации)
    df['vol_ma'] = df['volume'].rolling(vol_period, min_periods=1).mean()
    df['vol_signal'] = (df['volume'] > df['vol_ma']).astype(int)
    
    return df


def check_entry(prev_z, curr_z, z_threshold):
    """
    Вход при возврате к SMA.
    
    Returns:
        'long' если был long и теперь выходим
        'short' если был short и теперь выходим
        None если нет позиции или нет сигнала
    """
    # Возврат к SMA из long (z > threshold → z < threshold)
    if prev_z > z_threshold and curr_z < z_threshold:
        return 'short'
    # Возврат к SMA из short (z < -threshold → z > -threshold)
    if prev_z < -z_threshold and curr_z > -z_threshold:
        return 'long'
    return None


def check_exit(prev_z, curr_z, z_threshold, direction):
    """
    Выход при достижении экстремума Z-score.
    
    Args:
        direction: 'long' или 'short'
    
    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        # Из long выходим когда Z ушёл сильно вниз
        return curr_z < -z_threshold
    else:
        # Из short выходим когда Z ушёл сильно вверх
        return curr_z > z_threshold


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, sma_period, z_threshold, sl_points, tp_points, point,
             tick_value, tick_size, vol_period=20, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Z-score reversion.
    
    Args:
        df: DataFrame с OHLCV
        sma_period: период SMA
        z_threshold: порог Z-score для входа
        sl_points: SL в пунктах
        tp_points: TP в пунктах
        point: размер пункта
        tick_value: стоимость тика
        tick_size: размер тика
        vol_period: период для объёма
        sim_lot: размер лота
        spread_points: спред в пунктах
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_zscore(df, sma_period, z_threshold, vol_period)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_z = df['zscore'].iloc[i - 1]
        curr_z = df['zscore'].iloc[i]
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
                elif check_exit(prev_z, curr_z, z_threshold, 'long'):
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
                elif check_exit(prev_z, curr_z, z_threshold, 'short'):
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
            # Вход при возврате к SMA после экстремума
            if prev_z > z_threshold and curr_z < z_threshold:
                entry = curr_close + spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}
            elif prev_z < -z_threshold and curr_z > -z_threshold:
                entry = curr_close - spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}

    return profit, n_trades, trade_profits
