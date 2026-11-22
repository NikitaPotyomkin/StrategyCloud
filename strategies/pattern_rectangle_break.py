"""Pattern: Rectangle Breakout (H1).

Idea: 0175 pattern_rectangle_break
Вход: breakout rectangle (3+ touches)
Выход: height of rectangle
Отличие: Multiple level confirmation
"""
import numpy as np
import pandas as pd


def calc_pattern_rectangle_break(df, period=20):
    high_20 = df['high'].rolling(period).max()
    low_20 = df['low'].rolling(period).min()
    
    k = np.zeros(len(df))
    k[(df['close'] > high_20.shift(1))] = 1
    k[(df['close'] < low_20.shift(1))] = -1
    
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # k здесь двузначный (только ±1): нулевого состояния после прогрева нет,
    # поэтому prev == 0 не наступает никогда и стратегия не входила вовсе.
    # Вход по СМЕНЕ состояния — как в _bt_core.state_entry / живом движке.
    if curr == 1 and prev != 1:
        return 'long'
    if curr == -1 and prev != -1:
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
    return run_backtest(df, calc_pattern_rectangle_break, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
