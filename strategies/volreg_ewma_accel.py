"""Volatility Regime: EWMA Vol Acceleration (H1).

Idea: 0006 volreg_ewma_accel
Вход: EWMA-vol(0.94) выросла 2x к медиане(200)
Выход: return ниже 8 баров
Отличие: EWMA-волатильность вместо ATR, экспоненциальное сглаживание
"""
import numpy as np
import pandas as pd


def calc_volreg_ewma_accel(df, period=50):
    """EWMA volatility acceleration."""
    ret = df['close'].pct_change()

    # (right) EWMA vol с alpha=0.94
    alpha = 0.94
    ewma_vol = pd.Series(0.0, index=df.index)
    ewma_vol.iloc[0] = ret.iloc[0].abs()
    for i in range(1, len(df)):
        ewma_vol.iloc[i] = alpha * ret.iloc[i].abs() + (1 - alpha) * ewma_vol.iloc[i-1]

    # медиана за period баров
    med_vol = ewma_vol.rolling(period).median()

    ratio = ewma_vol / (med_vol + 1e-12)

    k = np.zeros(len(df))
    k[ratio > 2.0] = 1   # волатильность выросла 2x
    k[ratio < 0.5] = -1  # волатильность упала

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
    return run_backtest(df, calc_volreg_ewma_accel, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
