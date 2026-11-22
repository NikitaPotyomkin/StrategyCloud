"""Portfolio Layer: Live Sharpe Rank (H1).

Idea: 0962 port_live_sharpe_rank
Вход: ранжирование по живому Sharpe(20 сделок);
      выход: выпадение из топ-N.
Отличие: live Sharpe > бэктест Sharpe = стратегия работает лучше ожидаемого.

Правка 12.11.2026: Это фильтр, не входной сигнал.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_port_live_sharpe_rank(df, period=20):
    ret = df['close'].pct_change().fillna(0)

    # Rolling Sharpe = mean / std
    mean_ret = ret.rolling(period).mean()
    std_ret = ret.rolling(period).std()

    sharpe = mean_ret / std_ret.replace(0, np.nan).fillna(0)

    # Rank по скользящему окну
    sharpe_rank = sharpe.rolling(period * 2).rank(pct=True)

    # Топ-30% = разрешаем торговлю
    k = np.zeros(len(df))
    k[sharpe_rank > 0.7] = 1
    k[sharpe_rank < 0.3] = -1

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
    return run_backtest(df, calc_port_live_sharpe_rank, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
