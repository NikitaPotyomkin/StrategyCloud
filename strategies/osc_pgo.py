"""Oscillator: Pretty Good Oscillator (H1).

Idea: 0359 osc_pgo
Вход: PGO > 3 и растёт 3 бара
Выход: PGO < 0
Отличие: Отклонение цены от SMA, нормированное на среднюю цену
"""
import numpy as np
import pandas as pd


def calc_osc_pgo(df, period=14):
    """Pretty Good Oscillator от Джона Эллса."""
    sma = df['close'].rolling(period).mean()
    mad = df['close'].rolling(period).apply(lambda x: abs(x - x.mean()).mean())
    mad = mad.replace(0, np.nan).ffill()

    pgo = (df['close'] - sma) / (mad + 1e-12)

    # (right) PGO > 3 и растёт 3 бара подряд
    pgo_rising = (pgo > pgo.shift(1)) & (pgo.shift(1) > pgo.shift(2))
    k = np.zeros(len(df))
    k[(pgo > 3) & pgo_rising] = 1
    k[(pgo < -3) & (pgo < pgo.shift(1)) & (pgo.shift(1) < pgo.shift(2))] = -1

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
def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    """Симуляция через общий движок strategies/_bt_core.run_backtest.

    Вход по open следующего бара ± спред, спред вычитается и на выходе, обрыва
    по времени нет, деньги через trade_profit (÷ tick_size). Прежняя петля
    входила по close сигнального бара, не вычитала спред, выбрасывала сделки,
    не закрывшиеся за 49 баров, и считала P&L без деления на tick_size —
    из-за этого её числа были несравнимы с остальным реестром.
    """
    return run_backtest(df, calc_osc_pgo, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
