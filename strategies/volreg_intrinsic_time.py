"""Volatility Regime: Intrinsic Time (H1).

Idea: 0015 volreg_intrinsic_time
Вход: накопленный «истинный диапазон» > N x медианы — вход по знаку бара
Выход: 1 единица intrinsic time
Отличие: Каждый бар весится по своему диапазону, а не 1:1
"""
import numpy as np
import pandas as pd


def calc_volreg_intrinsic_time(df, period=20):
    """Intrinsic time — накопление True Range."""
    tr = df['high'] - df['low']
    median_tr = tr.rolling(period).median()

    # (right) intrinsic time step = tr / median_tr
    step = tr / (median_tr + 1e-12)

    # накапливаем
    cum_step = step.cumsum()

    # (right) знак текущего бара
    bar_sign = np.sign(df['close'] - df['open'])

    k = np.zeros(len(df))
    # (right) вход когда cum_step пробивает порог N
    threshold = period * 3  # 3 единицы intrinsic time
    k[cum_step > threshold] = 1
    k[cum_step < -threshold] = -1

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
    return run_backtest(df, calc_volreg_intrinsic_time, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
