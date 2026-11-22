"""Mom ROC of ROC (H1).

Idea: Second derivative of price momentum - ROC of ROC confirms trend acceleration
Вход: ROC(ROC(20)) > 0 and ROC(20) > 0 (long) or both < 0 (short)
Выход: k flips from 1 to 0 (long) or -1 to 0 (short)
Отличие: Double momentum filter eliminates weak trends, only strong acceleration trades
"""
import numpy as np
import pandas as pd


def calc_mom_roc_of_roc(df, period=20):
    """Calculate signal. Returns df with 'k' column."""
    k = np.zeros(len(df))
    close = df['close'].values
    # (right) First ROC: (close - close.shift(period)) / close.shift(period)
    roc1 = np.zeros(len(close))
    for i in range(period, len(close)):
        roc1[i] = (close[i] - close[i-period]) / close[i-period]
    # (right) Second ROC: ROC of ROC1
    roc2 = np.zeros(len(close))
    for i in range(period, len(close)):
        if roc1[i-period] != 0:
            roc2[i] = (roc1[i] - roc1[i-period]) / roc1[i-period]
        else:
            roc2[i] = 0
    # (right) k=1: both ROC1 > 0 and ROC2 > 0 (accelerating uptrend)
    k = np.where((roc1 > 0) & (roc2 > 0), 1, k)
    # (right) k=-1: both ROC1 < 0 and ROC2 < 0 (accelerating downtrend)
    k = np.where((roc1 < 0) & (roc2 < 0), -1, k)
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
    return run_backtest(df, calc_mom_roc_of_roc, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
