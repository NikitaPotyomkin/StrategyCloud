"""Chaikin Money Flow (CMF), каталог #91.

Сигнал: CMF > 0 при повышенном объёме → LONG; CMF < 0 при повышенном объёме → SHORT.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

VOL_MULT = 1.0


def calc_cmf(df, period):
    """period — окно CMF. Колонка 'k' — состояние позиции."""
    rng = (df['high'] - df['low']).replace(0.0, np.nan)
    mfm = ((df['close'] - df['low']) - (df['high'] - df['close'])) / rng
    mfv = (mfm.fillna(0.0) * df['volume'])
    vol_sum = df['volume'].rolling(period, min_periods=period).sum().replace(0.0, np.nan)
    cmf = mfv.rolling(period, min_periods=period).sum() / vol_sum
    cmf = cmf.fillna(0.0)
    vol_avg = df['volume'].rolling(period, min_periods=period).mean()
    vol_ok = df['volume'] > VOL_MULT * vol_avg
    up = (cmf > 0) & vol_ok
    dn = (cmf < 0) & vol_ok
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
    return run_backtest(df, calc_cmf, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
