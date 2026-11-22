"""Oscillator: Mass Index (H1).

Idea: 0332 osc_mass_index
Вход: Mass Index > 27 then falls
Выход: < 26
Отличие: Reversal detection via high/low range
"""
import numpy as np
import pandas as pd


def calc_osc_mass_index(df, period=25):
    hl_range = np.log(df['high'] / df['low'])
    ema1 = hl_range.ewm(span=9).mean()
    ema2 = ema1.ewm(span=9).mean()
    ratio = ema1 / ema2.replace(0, np.nan)
    mass = ratio.rolling(period).sum()
    
    k = np.zeros(len(df))
    k[(mass > 27) & (mass < mass.shift(1))] = 1
    k[(mass < 26) & (df['close'] < df['close'].shift(1))] = -1
    
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
    return run_backtest(df, calc_osc_mass_index, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
