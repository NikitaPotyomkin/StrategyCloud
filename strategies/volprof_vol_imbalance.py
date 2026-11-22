"""VolProf Vol Imbalance (H1).

Idea: Volume imbalance between up-bars and down-bars signals institutional activity
Вход: up_volume / down_volume > 1.5 (buying pressure) or < 0.67 (selling pressure)
Выход: k flips from 1 to 0 (long) or -1 to 0 (short)
Отличие: Uses volume-weighted classification of bars as up or down
"""
import numpy as np
import pandas as pd


def calc_volprof_vol_imbalance(df, period=20):
    """Calculate signal. Returns df with 'k' column."""
    k = np.zeros(len(df))
    close = df['close'].values
    open_ = df['open'].values
    volume = df['volume'].values
    # (right) Classify bars as up or down
    up_vol = np.zeros(len(close))
    down_vol = np.zeros(len(close))
    for i in range(len(close)):
        if close[i] >= open_[i]:
            up_vol[i] = volume[i]
        else:
            down_vol[i] = volume[i]
    # (right) Rolling sums over period
    up_vol_sum = np.zeros(len(close))
    down_vol_sum = np.zeros(len(close))
    for i in range(period, len(close)):
        up_vol_sum[i] = np.sum(up_vol[i-period:i])
        down_vol_sum[i] = np.sum(down_vol[i-period:i])
    # (right) Imbalance ratio
    ratio = np.zeros(len(close))
    for i in range(period, len(close)):
        if down_vol_sum[i] > 0:
            ratio[i] = up_vol_sum[i] / down_vol_sum[i]
        else:
            ratio[i] = 2.0  # (right) all up bars, extreme bullish
    # (right) k=1: ratio > 1.5 (buying pressure)
    k = np.where(ratio > 1.5, 1, k)
    # (right) k=-1: ratio < 0.67 (selling pressure)
    k = np.where(ratio < 0.67, -1, k)
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
    return run_backtest(df, calc_volprof_vol_imbalance, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
