"""Oscillator: Fisher Transform (H1).

Idea: 0321 osc_fisher_transform
Вход: Fisher > 1.5 и разворот сверху
Выход: Fisher < 0
Отличие: Экстремумы и развороты через трансформацию Фишера
"""
import numpy as np
import pandas as pd


def calc_osc_fisher_transform(df, period=10):
    """Fisher transform на медиане цены."""
    high_ = df['high'].rolling(period).max()
    low_ = df['low'].rolling(period).min()
    median = (high_ + low_) / 2.0

    # (right) clip для предотвращения log(0)
    v = 0.5 * ((df['close'] - low_) / (high_ - low_ + 1e-12) - 0.5)
    v = np.clip(v, -0.99, 0.99)

    fisher = pd.Series(0.0, index=df.index)
    for i in range(1, len(df)):
        fisher.iloc[i] = 0.5 * np.log((1 + v.iloc[i]) / (1 - v.iloc[i] + 1e-12)) + 0.5 * fisher.iloc[i-1]

    signal = fisher.shift(1)
    k = np.zeros(len(df))
    k[(fisher > 1.5) & (signal <= 1.5)] = 1    # разворот вниз
    k[(fisher < -1.5) & (signal >= -1.5)] = -1  # разворот вверх

    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Возвращает 'long' / 'short' / None для engine run_backtest
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
    return run_backtest(df, calc_osc_fisher_transform, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
