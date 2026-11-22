"""Channel: Median Band (H1).

Idea: 0214 chan_median_band
Вход: close above rolling-median + 1.5 MAD
Выход: median
Отличие: Robust median-based channel
"""
import numpy as np
import pandas as pd


def calc_chan_median_band(df, period=50):
    median = df['close'].rolling(period).median()
    mad = (df['close'] - median).abs().rolling(period).mean()
    
    upper = median + 1.5 * mad
    lower = median - 1.5 * mad
    
    k = np.zeros(len(df))
    k[df['close'] > upper] = 1
    k[df['close'] < lower] = -1
    
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
    return run_backtest(df, calc_chan_median_band, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
