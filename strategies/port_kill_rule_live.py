"""Portfolio Layer: Kill Rule Live (H1).

Idea: 0984 port_kill_rule_live
Вход: правила выключения: live PnL < -2% квоты -> стоп;
      выход: восстановление.
Отличие: kill rule предотвращает катастрофические потери.

Правка 12.11.2026: Это фильтр, не входной сигнал.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_port_kill_rule_live(df, period=50):
    ret = df['close'].pct_change().fillna(0)

    # Rolling drawdown
    cum_ret = (1 + ret).cumprod()
    rolling_max = cum_ret.expanding().max()
    drawdown = (cum_ret - rolling_max) / rolling_max

    # Kill: DD < -2%
    is_killed = drawdown < -0.02

    # Восстановление: DD > -1%
    is_recovered = drawdown > -0.01

    k = np.zeros(len(df))
    k[~is_killed & ~is_recovered & (ret > 0)] = 1
    k[~is_killed & ~is_recovered & (ret < 0)] = -1
    k[is_killed] = 0  # Kill: не торговать
    k[is_recovered] = 1  # Recovery: возвращаемся

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
    return run_backtest(df, calc_port_kill_rule_live, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
