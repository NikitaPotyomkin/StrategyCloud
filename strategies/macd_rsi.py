"""Стратегия MACD + RSI Combo.

Вход: MACD пересекает сигнальную линию вверх И RSI < 30 (перепроданность) → long;
      MACD пересекает сигнальную линию вниз И RSI > 70 (перекупленность) → short.
Выход: разворот гистограммы MACD.
"""
import numpy as np
import pandas as pd


def calc_macd_rsi(df, macd_fast=12, macd_slow=26, macd_signal=9, rsi_period=14,
                  rsi_oversold=30, rsi_overbought=70):
    """Добавляет колонку 'signal' на основе MACD + RSI."""
    df = df.copy()

    # MACD
    ema_fast = df['close'].ewm(span=macd_fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=macd_slow, adjust=False).mean()
    df['macd'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd'].ewm(span=macd_signal, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(rsi_period).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))

    # Комбо-сигнал: MACD crossover + RSI condition
    df['signal'] = 0
    # Long: MACD пересекает сигнальную линию вверх И RSI < rsi_oversold
    long_cond = (df['macd'] > df['macd_signal']) & \
                (df['macd'].shift(1) <= df['macd_signal'].shift(1)) & \
                (df['rsi'] < rsi_oversold)
    # Short: MACD пересекает сигнальную линию вниз И RSI > rsi_overbought
    short_cond = (df['macd'] < df['macd_signal']) & \
                 (df['macd'].shift(1) >= df['macd_signal'].shift(1)) & \
                 (df['rsi'] > rsi_overbought)
    df.loc[long_cond, 'signal'] = 1
    df.loc[short_cond, 'signal'] = -1

    return df


def check_entry_macd_rsi(prev_signal, curr_signal):
    """Вход по смене сигнала."""
    if prev_signal == 0 and curr_signal == 1:
        return 'long'
    if prev_signal == 0 and curr_signal == -1:
        return 'short'
    return None


def check_exit_macd_rsi(prev_signal, curr_signal, direction):
    """Выход при развороте сигнала."""
    if direction == 'long':
        return curr_signal == -1
    return curr_signal == 1


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest_macd_rsi(df, macd_fast, macd_slow, macd_signal, rsi_period,
                      rsi_oversold, rsi_overbought, sl_points, tp_points,
                      point, tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """Симуляция сделок на истории с MACD + RSI.
    
    Возвращает (profit, n_trades, trade_profits).
    """
    df = calc_macd_rsi(df, macd_fast, macd_slow, macd_signal,
                       rsi_period, rsi_oversold, rsi_overbought)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['signal'].iloc[i - 1]
        curr_signal = df['signal'].iloc[i]
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
                elif check_exit_macd_rsi(prev_signal, curr_signal, 'long'):
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
                elif check_exit_macd_rsi(prev_signal, curr_signal, 'short'):
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
            entry_dir = check_entry_macd_rsi(prev_signal, curr_signal)
            if entry_dir == 'long':
                entry = curr_close + spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close - spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits


# Алиасы для совместимости с IDE-референсами
check_entry = check_entry_macd_rsi
check_exit = check_exit_macd_rsi
