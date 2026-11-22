"""Oscillator: RVI (Relative Volatility Index) (H1).

Idea: 0330 osc_rvi_hlc
Вход: RVI кросс сигнальной линии
Выход: обратный кросс
Отличие: Волатильность вверх/вниз вместо цены
"""
import numpy as np
import pandas as pd


def calc_osc_rvi_hlc(df, period=10):
    """Relative Volatility Index — аналог RSI для волатильности."""
    up_move = df['high'].diff()
    down_move = df['low'].diff()

    up_vol = up_move.where(up_move > 0, 0.0).abs()
    down_vol = down_move.where(down_move < 0, 0.0).abs()

    avg_up = up_vol.rolling(period).mean()
    avg_down = down_vol.rolling(period).mean()

    rvi = 100 * avg_up / (avg_up + avg_down + 1e-12)
    signal = rvi.rolling(3).mean()

    k = np.zeros(len(df))
    k[(rvi > signal) & (rvi.shift(1) <= signal.shift(1))] = 1
    k[(rvi < signal) & (rvi.shift(1) >= signal.shift(1))] = -1

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
    return run_backtest(df, calc_osc_rvi_hlc, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
