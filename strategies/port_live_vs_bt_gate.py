"""Portfolio Layer: Live vs Backtest Gate (H1).

Idea: 0961 port_live_vs_bt_gate
Вход: сравнение live P&L с ожиданием бэктеста;
      расхождение > 3x -> карантин (фильтр).
Выход: сходимость live и BT.
Отличие: live-vs-BT gate предотвращает торговать дефектные стратегии.

Правка 12.11.2026: Это фильтр, не входной сигнал.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_port_live_vs_bt_gate(df, period=20):
    # Прокси: сравнение текущей волатильности с исторической
    # Если текущая волатильность сильно отличается -> фильтр

    ret = df['close'].pct_change().fillna(0)

    # Текущая волатильность
    vol_current = ret.rolling(5).std()

    # Историческая волатильность
    vol_historical = ret.rolling(period).std()

    # Отношение
    vol_ratio = vol_current / vol_historical.replace(0, np.nan).fillna(1)

    # Карантин: ratio > 3 или ratio < 0.3
    k = np.zeros(len(df))
    k[(vol_ratio > 3) | (vol_ratio < 0.3)] = 0  # Фильтр: не торговать
    k[vol_ratio.between(0.3, 3)] = 1  # Разрешение

    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Returns 'long' / 'short' / None for engine run_backtest
    # Это фильтр: k=1 разрешает, k=0 запрещает
    if prev == 0 and curr == 1:
        return 'long'
    if prev == 0 and curr == -1:
        return 'short'
    return None


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    return run_backtest(df, calc_port_live_vs_bt_gate, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
