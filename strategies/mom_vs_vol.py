"""Momentum: vs Volatility (H1).

Idea: 0285 mom_vs_vol
Вход: momentum(20)/σ(20) > 1.5
Выход: < 0
Отличие: Risk-adjusted momentum
"""
import numpy as np
import pandas as pd


def calc_mom_vs_vol(df, period=20):
    mom = df['close'] - df['close'].shift(period)
    vol = df['close'].rolling(period).std()
    mom_vol_ratio = mom / vol.replace(0, np.nan)
    
    k = np.zeros(len(df))
    k[mom_vol_ratio > 1.5] = 1
    k[mom_vol_ratio < -1.5] = -1
    
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
    return run_backtest(df, calc_mom_vs_vol, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
