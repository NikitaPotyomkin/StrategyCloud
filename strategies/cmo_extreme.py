"""CMO extreme, каталог #78.

Сигнал: Chande Momentum Oscillator > 50 → LONG, < −50 → SHORT.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

THRESHOLD = 50.0


def calc_cmo(df, period):
    """period — окно CMO. Колонка 'k' — состояние позиции."""
    delta = df['close'].diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1.0 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1.0 / period, adjust=False).mean()
    denom = (gain + loss).replace(0.0, np.nan)
    cmo = 100.0 * (gain - loss) / denom
    cmo = cmo.fillna(0.0)
    up = cmo > THRESHOLD
    dn = cmo < -THRESHOLD
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
    return run_backtest(df, calc_cmo, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
