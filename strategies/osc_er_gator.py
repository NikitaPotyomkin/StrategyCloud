"""Oscillator: Gator (H1).

Idea: 0360 osc_er_gator
Вход: Gator — BB width vs Keltner, расширение
Выход: сужение
Отличие: Визуальный осциллятор для сжатия/расширения волатильности
"""
import numpy as np
import pandas as pd


def calc_osc_er_gator(df, period=20):
    """Gator Oscillator — разница между BB width и Keltner width."""
    mid = df['close'].rolling(period).mean()
    std = df['close'].rolling(period).std()
    bb_upper = mid + 2 * std
    bb_lower = mid - 2 * std
    bb_width = bb_upper - bb_lower

    atr = df['high'].rolling(period).max() - df['low'].rolling(period).min()
    kelt_width = 2 * atr

    gator = bb_width - kelt_width

    k = np.zeros(len(df))
    k[gator > gator.rolling(3).mean().shift(1)] = 1   # расширение
    k[gator < gator.rolling(3).mean().shift(1)] = -1  # сужение

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
    return run_backtest(df, calc_osc_er_gator, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
