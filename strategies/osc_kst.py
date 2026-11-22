"""Oscillator: KST (H1).

Idea: 0334 osc_kst
Вход: KST crosses signal up
Выход: down
Отличие: Know Sure Thing - sum of weighted ROCs
"""
import numpy as np
import pandas as pd


def calc_osc_kst(df, period=9):
    roc10 = df['close'].pct_change(10)
    roc15 = df['close'].pct_change(15)
    roc20 = df['close'].pct_change(20)
    roc30 = df['close'].pct_change(30)
    
    kst = (roc10 * 1 + roc15 * 2 + roc20 * 3 + roc30 * 4) / 10
    signal = kst.rolling(period).mean()
    
    k = np.zeros(len(df))
    k[(kst > signal) & (kst.shift(1) <= signal.shift(1))] = 1
    k[(kst < signal) & (kst.shift(1) >= signal.shift(1))] = -1
    
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
    return run_backtest(df, calc_osc_kst, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
