"""Volatility: NR7 Breakout (H1).

Idea: 0019 volreg_nr7_break
Вход: NR7 (narrowest bar in 7) + breakout
Выход: trail 2xATR
Отличие: Narrow Range 7 pattern
"""
import numpy as np
import pandas as pd


def calc_volreg_nr7_break(df, n=7):
    tr = np.maximum(df['high'] - df['low'], np.abs(df['high'] - df['close'].shift(1)))
    range_7 = tr.rolling(n).min()
    is_nr7 = tr == range_7
    
    high_7 = df['high'].rolling(n).max()
    low_7 = df['low'].rolling(n).min()
    
    k = np.zeros(len(df))
    k[(is_nr7) & (df['close'] > high_7.shift(1))] = 1
    k[(is_nr7) & (df['close'] < low_7.shift(1))] = -1
    
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
    return run_backtest(df, calc_volreg_nr7_break, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
