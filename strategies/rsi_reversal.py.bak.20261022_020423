import numpy as np
import pandas as pd


def calc_rsi_reversal(df, rsi_period=14, rsi_oversold=30, rsi_overbought=70):
    df = df.copy()

    # RSI по Уайдеру
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/rsi_period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/rsi_period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))

    # Вход на ВЫХОДЕ из зоны, не на входе в неё
    df['signal'] = 0
    long_cond = (df['rsi'] > rsi_oversold) & (df['rsi'].shift(1) <= rsi_oversold)
    short_cond = (df['rsi'] < rsi_overbought) & (df['rsi'].shift(1) >= rsi_overbought)
    df.loc[long_cond, 'signal'] = 1
    df.loc[short_cond, 'signal'] = -1

    # Фильтр тренда: EMA(200) на close
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['trend'] = np.where(df['close'] > df['ema200'], 1, -1)

    return df


def check_entry_rsi_reversal(prev_signal, curr_signal, curr_trend):
    """Вход только по тренду."""
    if prev_signal == 0 and curr_signal == 1 and curr_trend == 1:
        return 'long'
    if prev_signal == 0 and curr_signal == -1 and curr_trend == -1:
        return 'short'
    return None


def check_exit_rsi_reversal(rsi_value, direction, exit_level=50):
    """Выход при возврате RSI к 50."""
    if direction == 'long':
        return rsi_value >= exit_level
    return rsi_value <= exit_level


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest_rsi_reversal(df, rsi_period, rsi_oversold, rsi_overbought,
                          sl_points, tp_points, point, tick_value, tick_size,
                          sim_lot=0.01, spread_points=0):
    df = calc_rsi_reversal(df, rsi_period, rsi_oversold, rsi_overbought)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(max(rsi_period + 1, 201), len(df)):
        prev_signal = df['signal'].iloc[i - 1]
        curr_signal = df['signal'].iloc[i]
        curr_close = df['close'].iloc[i]
        curr_rsi = df['rsi'].iloc[i]
        curr_trend = df['trend'].iloc[i]
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]

        # ── Выход ──
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
                elif check_exit_rsi_reversal(curr_rsi, 'long'):
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
                elif check_exit_rsi_reversal(curr_rsi, 'short'):
                    p = _profit(position['entry'], curr_close,
                                tick_value, tick_size, sim_lot, 'short')
                    exited = True

            if exited:
                p -= (spread / tick_size) * tick_value * sim_lot
                profit += p
                n_trades += 1
                trade_profits.append(p)
                position = None

        # ── Вход ──
        if position is None:
            entry_dir = check_entry_rsi_reversal(prev_signal, curr_signal, curr_trend)
            if entry_dir == 'long':
                entry = curr_close + spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close - spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits


check_entry = check_entry_rsi_reversal
check_exit = check_exit_rsi_reversal
