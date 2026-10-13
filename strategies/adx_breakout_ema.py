"""ADX breakout + EMA, каталог #74.

Сигнал: ADX > 30 и цена выше/ниже EMA(50) → трендовый вход.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

ADX_THRESHOLD = 30.0
EMA_PERIOD = 50


def _adx(df, period):
    """ADX (Wilder)."""
    high, low, close = df['high'], df['low'], df['close']
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    prev_close = close.shift(1)
    tr = pd.concat([high - low,
                    (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean().replace(0.0, np.nan)
    plus_di = 100.0 * plus_dm.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean() / atr
    minus_di = 100.0 * minus_dm.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean() / atr
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean().fillna(0.0)


def calc_adx_breakout_ema(df, period):
    """period — период ADX. Колонка 'k' — состояние позиции."""
    adx = _adx(df, period)
    ema = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    strong = adx > ADX_THRESHOLD
    up = strong & (df['close'] > ema)
    dn = strong & (df['close'] < ema)
    df = df.copy()
    df['k'] = np.where(up, 1, np.where(dn, -1, 0))
    return df


def check_entry(prev_s, curr_s):
    return state_entry(prev_s, curr_s)


def check_exit(prev_s, curr_s, direction):
    return state_exit(prev_s, curr_s, direction)


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_adx_breakout_ema, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
