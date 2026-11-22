"""Volatility Regime: BB Width Percentile Low (H1).

Idea: 0008 volreg_bbw_pct_low
Вход: BBW(20) < p10(240) and close outside BB(2.0)
Выход: mid-BB
Отличие: Bollinger Band width compression breakout
"""
import numpy as np
import pandas as pd


def calc_volreg_bbw_pct_low(df, period=20):
    sma = df['close'].rolling(20).mean()
    std = df['close'].rolling(20).std()
    upper = sma + 2.0 * std
    lower = sma - 2.0 * std
    bbw = (upper - lower) / sma
    
    p10 = bbw.rolling(240).quantile(0.10)
    outside = (df['close'] > upper) | (df['close'] < lower)
    
    k = np.zeros(len(df))
    k[(bbw < p10) & (df['close'] > upper)] = 1
    k[(bbw < p10) & (df['close'] < lower)] = -1
    
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
    return run_backtest(df, calc_volreg_bbw_pct_low, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
