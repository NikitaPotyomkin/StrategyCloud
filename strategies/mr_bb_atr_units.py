"""Mean Reversion: BB ATR Units (H1).

Idea: 0881 mr_bb_atr_units
Вход: цена дальше 2 ATR от средней BB
Выход: средняя BB
Отличие: Отклонение в ATR-единицах вместо стандартных отклонений
"""
import numpy as np
import pandas as pd


def calc_mr_bb_atr_units(df, param_key):
    """Цена > 2 ATR от BB middle."""
    parts = str(param_key).split(',') if isinstance(param_key, str) else [str(param_key)]
    bb_period = int(parts[0]) if len(parts) > 0 else 20
    atr_mult = float(parts[1]) if len(parts) > 1 else 2.0
    mid = df['close'].rolling(bb_period).mean()
    std = df['close'].rolling(bb_period).std()
    bb_upper = mid + 2 * std
    bb_lower = mid - 2 * std

    atr = (df['high'] - df['low']).rolling(bb_period).mean()

    dist_upper = (df['close'] - mid) / (atr + 1e-12)
    dist_lower = (mid - df['close']) / (atr + 1e-12)

    k = np.zeros(len(df))
    k[dist_upper > atr_mult] = 1   # цена выше верхней границы ATR
    k[dist_lower > atr_mult] = -1  # цена ниже нижней границы ATR

    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Возвращает 'long' / 'short' / None для engine run_backtest
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
    bb_period = int(parts[0]) if len(parts) > 0 else 20
    atr_mult = float(parts[1]) if len(parts) > 1 else 2.0
    return calc_mr_bb_atr_units(df, f"{bb_period},{atr_mult}")


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
