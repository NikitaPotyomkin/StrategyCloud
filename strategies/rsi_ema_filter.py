"""RSI + EMA trend filter (каталог #28).

Сигнал: RSI-импульс в направлении тренда EMA(period) — RSI>50 при цене выше EMA = LONG,
RSI<50 при цене ниже EMA = SHORT.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 / -1 при согласии RSI и EMA, иначе 0.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_rsi_ema(df, period):
    """period — окно EMA-фильтра (RSI с периодом 14). Колонка 'k' — состояние."""
    delta = df['close'].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)
    ema = df['close'].ewm(span=period, adjust=False).mean()
    state = np.where((rsi > 50.0) & (df['close'] > ema), 1,
                     np.where((rsi < 50.0) & (df['close'] < ema), -1, 0))
    df = df.copy()
    df['k'] = state
    return df


def check_entry(prev_s, curr_s):
    return state_entry(prev_s, curr_s)


def check_exit(prev_s, curr_s, direction):
    return state_exit(prev_s, curr_s, direction)


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_rsi_ema, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
