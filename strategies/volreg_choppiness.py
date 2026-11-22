"""Volatility: Choppiness Index (H1).

Idea: 0011 volreg_choppiness
Вход: Choppiness(14) < 38 and close > SMA(100)
Выход: Choppiness > 62
Отличие: Choppiness index for trend detection
"""
import numpy as np
import pandas as pd


def calc_volreg_choppiness(df, period=14):
    tr = np.maximum(df['high'] - df['low'], np.abs(df['high'] - df['close'].shift(1)))
    sum_tr = tr.rolling(period).sum()
    diff_close = df['high'].rolling(period).max() - df['low'].rolling(period).min()
    
    choppiness = 100 * np.log10(sum_tr / diff_close.replace(0, np.nan)) / np.log10(period)
    
    sma_100 = df['close'].rolling(100).mean()
    
    k = np.zeros(len(df))
    k[(choppiness < 38) & (df['close'] > sma_100)] = 1
    k[(choppiness > 62)] = -1
    
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
    return run_backtest(df, calc_volreg_choppiness, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
