"""Volatility: WR7 Fade (H1).

Iidea: 0020 volreg_wr7_fade
Вход: WR7 (widest bar in 7) + return inside
Выход: SMA(20)
Отличие: Wide Range 7 reversal
"""
import numpy as np
import pandas as pd


def calc_volreg_wr7_fade(df, n=7):
    tr = np.maximum(df['high'] - df['low'], np.abs(df['high'] - df['close'].shift(1)))
    range_7 = tr.rolling(n).max()
    is_wr7 = tr == range_7
    
    sma_20 = df['close'].rolling(20).mean()
    
    k = np.zeros(len(df))
    k[(is_wr7) & (df['close'] < sma_20)] = 1  # fade up
    k[(is_wr7) & (df['close'] > sma_20)] = -1  # fade down
    
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
    return run_backtest(df, calc_volreg_wr7_fade, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
