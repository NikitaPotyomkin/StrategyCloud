"""Стратегия ADX Trend — вход по силе тренда ADX и направлению DI+/DI−."""
import numpy as np
import pandas as pd


def calc_adx(df, period=14, adx_threshold=25):
    """
    Добавляет колонки 'adx', 'di_plus', 'di_minus' с индикаторами ADX и сигналом.
    
    Args:
        df: DataFrame с OHLCV
        period: период для расчёта ADX
        adx_threshold: пороговое значение ADX для подтверждения тренда
    
    Returns:
        DataFrame с колонками 'adx', 'di_plus', 'di_minus', 'adx_signal'
    """
    df = df.copy()
    
    # True Range
    tr1 = df['high'] - df['low']
    tr2 = abs(df['high'] - df['close'].shift())
    tr3 = abs(df['low'] - df['close'].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    
    # Directional Movement
    up_move = df['high'] - df['high'].shift()
    down_move = df['low'].shift() - df['low']
    
    di_plus = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    di_minus = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    # Сглаживание DI (исправляем NaN в ATR)
    atr_safe = atr.fillna(atr.mean()) if atr.mean() > 0 else pd.Series(1.0, index=df.index)
    di_plus_smooth = pd.Series(di_plus).rolling(period).mean() / atr_safe * 100
    di_minus_smooth = pd.Series(di_minus).rolling(period).mean() / atr_safe * 100
    
    # Directional Index
    dx = np.where((di_plus_smooth + di_minus_smooth) != 0,
                  abs(di_plus_smooth - di_minus_smooth) / (di_plus_smooth + di_minus_smooth) * 100,
                  0)
    
    # ADX (сглаженная DX)
    adx = pd.Series(dx).rolling(period).mean()
    
    df['adx'] = adx
    df['di_plus'] = di_plus_smooth
    df['di_minus'] = di_minus_smooth
    
    # Сигнал: ADX > threshold + DI+ > DI- → LONG, ADX > threshold + DI- > DI+ → SHORT
    df['adx_signal'] = 0
    df.loc[(df['adx'] > adx_threshold) & (df['di_plus'] > df['di_minus']), 'adx_signal'] = 1
    df.loc[(df['adx'] > adx_threshold) & (df['di_minus'] > df['di_plus']), 'adx_signal'] = -1
    
    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при подтверждении тренда по ADX.
    
    Returns:
        'long', 'short' или None
    """
    # Long: был нейтральный или short-сигнал, теперь ADX подтверждает тренд вверх
    if prev_signal != 1 and curr_signal == 1:
        return 'long'
    # Short: был нейтральный или long-сигнал, теперь ADX подтверждает тренд вниз
    if prev_signal != -1 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при ослаблении тренда ADX или смене направления DI.
    
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


def backtest(df, period, adx_threshold, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с ADX Trend.
    
    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_adx(df, period, adx_threshold)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['adx_signal'].iloc[i - 1]
        curr_signal = df['adx_signal'].iloc[i]
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
