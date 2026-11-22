"""Regime: Vol Switch (H1).

Idea: 0535 regime_vol_switch
Вход: σ(20)/σ(100) crosses 1 from below
Выход: back below 1
Отличие: Volatility regime change detection
"""
import numpy as np
import pandas as pd


def calc_regime_vol_switch(df, period=20):
    vol_20 = df['close'].pct_change().rolling(20).std()
    vol_100 = df['close'].pct_change().rolling(100).std()
    ratio = vol_20 / vol_100.replace(0, np.nan)
    
    k = np.zeros(len(df))
    k[(ratio > 1) & (ratio.shift(1) <= 1)] = 1
    k[(ratio < 1) & (ratio.shift(1) >= 1)] = -1
    
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
    return run_backtest(df, calc_regime_vol_switch, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
