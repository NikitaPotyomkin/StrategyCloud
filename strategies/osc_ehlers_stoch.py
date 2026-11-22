"""Oscillator: Ehlers Stochastic (H1).

Idea: 0328 osc_ehlers_stoch
Вход: Ehlers Stochastic < 0.2
Выход: > 0.8
Отличие: Ehlers smoothing for stochastic
"""
import numpy as np
import pandas as pd


def calc_osc_ehlers_stoch(df, period=10):
    close_norm = (df['close'] - df['low'].rolling(period).min()) / (df['high'].rolling(period).max() - df['low'].rolling(period).min()).replace(0, np.nan)
    close_norm = close_norm.clip(0, 1)
    
    # Ehlers super smoother
    a1 = np.exp(-1.414 * np.pi / period)
    b1 = 2 * a1 * np.cos(1.414 * np.pi / period)
    c2 = b1
    c3 = -a1 * a1
    c1 = 1 - c2 - c3
    
    # (right) float64 вместо int64 — иначе TypeError при присваивании float в int Series
    smoothed = pd.Series(0.0, index=df.index, dtype=float)
    for i in range(period, len(df)):
        smoothed.iloc[i] = c1 * close_norm.iloc[i] + c2 * smoothed.iloc[i-1] + c3 * smoothed.iloc[i-2]
    
    k = np.zeros(len(df))
    k[smoothed < 0.2] = 1
    k[smoothed > 0.8] = -1
    
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
    return run_backtest(df, calc_osc_ehlers_stoch, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
