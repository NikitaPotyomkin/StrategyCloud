"""Pattern: Gap and Go (H1).

Idea: 0182 pattern_gap_go
Вход: gap with continuation
Выход: ADR
Отличие: Gap analysis for H1
"""
import numpy as np
import pandas as pd


def calc_pattern_gap_go(df, period=1):
    prev_close = df['close'].shift(1)
    gap = (df['open'] - prev_close) / prev_close
    atr = df['high'].rolling(14).mean() - df['low'].rolling(14).mean()
    
    k = np.zeros(len(df))
    k[(gap > 0.005) & (df['close'] > df['open'])] = 1
    k[(gap < -0.005) & (df['close'] < df['open'])] = -1
    
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
    return run_backtest(df, calc_pattern_gap_go, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
