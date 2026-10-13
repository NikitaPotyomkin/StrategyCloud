"""Ultimate Oscillator, каталог #32.

Сигнал: UO в зоне перепроданности при цене выше EMA(50) → LONG;
        UO в зоне перекупленности при цене ниже EMA(50) → SHORT.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

OVERSOLD = 30.0
OVERBOUGHT = 70.0
TREND_PERIOD = 50


def _uo(df, period):
    """UO с окнами period / 2·period / 4·period (стандарт 7/14/28)."""
    prev_close = df['close'].shift(1)
    bp = df['close'] - pd.concat([df['low'], prev_close], axis=1).min(axis=1)
    tr = (pd.concat([df['high'], prev_close], axis=1).max(axis=1)
          - pd.concat([df['low'], prev_close], axis=1).min(axis=1))
    tr = tr.replace(0.0, np.nan)

    def avg(n):
        return bp.rolling(n, min_periods=n).sum() / tr.rolling(n, min_periods=n).sum()

    uo = 100.0 * (4.0 * avg(period) + 2.0 * avg(2 * period) + avg(4 * period)) / 7.0
    return uo.fillna(50.0)


def calc_ultimate(df, period):
    """period — короткое окно UO. Колонка 'k' — состояние позиции."""
    uo = _uo(df, period)
    trend = df['close'].ewm(span=TREND_PERIOD, adjust=False).mean()
    up = (uo <= OVERSOLD) & (df['close'] > trend)
    dn = (uo >= OVERBOUGHT) & (df['close'] < trend)
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
    return run_backtest(df, calc_ultimate, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
