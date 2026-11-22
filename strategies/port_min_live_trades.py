"""Portfolio Layer: Min Live Trades Gate (H1).

Idea: 0967 port_min_live_trades
Вход: полная квота только после 15 живых сделок;
      probation: 15% квоты до 10 сделок.
Отличие: минимальный live-sample предотвращает overfitting.

Правка 12.11.2026: Это фильтр, не входной сигнал.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_port_min_live_trades(df, period=100):
    ret = df['close'].pct_change().fillna(0)

    # Прокси: считаем количество сигналов (переключений k)
    # В реальной системе это счётчик live сделок

    # Rolling count of signals
    signal_changes = ret.diff().abs()
    signal_count = signal_changes.rolling(period).sum()

    # После period баров разрешаем полную торговлю
    k = np.zeros(len(df))
    k[signal_count > 10] = 1  # Разрешаем после 10 сигналов
    k[signal_count.between(5, 10)] = 0  # Probation

    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Returns 'long' / 'short' / None for engine run_backtest
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
    return run_backtest(df, calc_port_min_live_trades, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
