"""Mom Pullback Ratio (H1).

Idea: After an impulse move, price pulls back less than 38% of the impulse
Вход: impulse detected, pullback < 38% of impulse (long) or pullback < 38% up (short)
Выход: k flips from 1 to 0 (long) or -1 to 0 (short)
Отличие: Measures pullback depth relative to preceding impulse magnitude
"""
import numpy as np
import pandas as pd


def calc_mom_pullback_ratio(df, period=20):
    """Calculate signal. Returns df with 'k' column."""
    k = np.zeros(len(df))
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    # (right) Find impulse: max(high) - min(low) over period
    impulse = np.zeros(len(close))
    imp_high = np.zeros(len(close))
    imp_low = np.zeros(len(close))
    for i in range(period, len(close)):
        impulse[i] = np.max(high[i-period:i]) - np.min(low[i-period:i])
        imp_high[i] = np.max(high[i-period:i])
        imp_low[i] = np.min(low[i-period:i])
    # (right) Pullback: from recent extreme to current
    # (right) k=1: after high impulse, pullback < 38% of impulse
    pullback_ratio = np.zeros(len(close))
    for i in range(period, len(close)):
        if impulse[i] > 0:
            pullback_ratio[i] = (imp_high[i] - close[i]) / impulse[i]
    # (right) k=1: pullback less than 38% of impulse (bullish continuation)
    k = np.where((pullback_ratio > 0) & (pullback_ratio < 0.38) & (impulse > 0), 1, k)
    # (right) k=-1: after low impulse, rally < 38% of impulse (bearish continuation)
    rally_ratio = np.zeros(len(close))
    for i in range(period, len(close)):
        if impulse[i] > 0:
            rally_ratio[i] = (close[i] - imp_low[i]) / impulse[i]
    k = np.where((rally_ratio > 0) & (rally_ratio < 0.38) & (impulse > 0), -1, k)
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
    return run_backtest(df, calc_mom_pullback_ratio, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
