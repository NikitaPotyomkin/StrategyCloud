"""Day-of-Week Momentum, каталог #96.

Сигнал: вход в направлении средней доходности текущего дня недели
(средняя — по последним `period` наблюдениям этого дня, без look-ahead).
Требует DatetimeIndex; иначе день недели = позиция по модулю 7.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def _weekday(df):
    idx = df.index
    if isinstance(idx, pd.DatetimeIndex):
        return idx.dayofweek.to_numpy()
    return (np.arange(len(df)) % 7).astype(np.int64)


def calc_day_of_week(df, period):
    """period — окно (в наблюдениях этого дня недели) для средней доходности. Колонка 'k'."""
    period = max(1, int(period))
    ret = df['close'].pct_change().fillna(0.0).to_numpy(dtype=float)
    wd = _weekday(df)
    # Группировка по массиву (не по индексу) — устойчива к дублирующемуся DatetimeIndex.
    mean_by_wd = (pd.Series(ret)
                  .groupby(wd)
                  .transform(lambda s: s.rolling(period, min_periods=period).mean().shift(1))
                  .fillna(0.0)
                  .to_numpy())
    state = np.where(mean_by_wd > 0, 1, np.where(mean_by_wd < 0, -1, 0))
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
    return run_backtest(df, calc_day_of_week, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
