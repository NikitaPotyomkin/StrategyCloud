"""Oscillator: RAVI (H1).

Idea: 0360 osc_ravi
Вход: RAVI (ROC MA 7/65) > 0.3%
Выход: RAVI < -0.3%
Отличие: ROC на скользящих средних — скорость изменения скорости
"""
import numpy as np
import pandas as pd


def calc_osc_ravi(df, fast=7, slow=65):
    """ROC Average Velocity Index."""
    roc = df['close'].pct_change(fast)
    roc_slow = df['close'].pct_change(slow)

    ma_fast = roc.rolling(fast).mean()
    ma_slow = roc_slow.rolling(slow).mean()

    ravi = (ma_fast - ma_slow) * 100  # в процентах

    k = np.zeros(len(df))
    k[ravi > 0.3] = 1
    k[ravi < -0.3] = -1

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


from strategies._bt_core import run_backtest
def _calc(df, param_key):
    """calc_* с параметрами, собранными из param_key."""
    parts = str(param_key).split(',') if isinstance(param_key, str) else [str(param_key)]
    fast = int(parts[0]) if len(parts) > 0 else 7
    slow = int(parts[1]) if len(parts) > 1 else 65
    return calc_osc_ravi(df, fast, slow)


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    """Симуляция через общий движок strategies/_bt_core.run_backtest.

    Вход по open следующего бара ± спред, спред вычитается и на выходе, обрыва
    по времени нет, деньги через trade_profit (÷ tick_size). Прежняя петля
    входила по close сигнального бара, не вычитала спред, выбрасывала сделки,
    не закрывшиеся за 49 баров, и считала P&L без деления на tick_size —
    из-за этого её числа были несравнимы с остальным реестром.
    """
    return run_backtest(df, _calc, check_entry, check_exit,
                        param_key, sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
