"""Oscillator: Klinger Volume Oscillator (H1).

Idea: 0349 osc_klinger
Вход: KVO > 0
Выход: < 0
Отличие: Volume-weighted oscillator
"""
import numpy as np
import pandas as pd


def calc_osc_klinger(df, period=34):
    roc = df['close'].pct_change(34).abs()
    signal = roc.ewm(span=55).mean()
    kvo = roc - signal
    
    k = np.zeros(len(df))
    k[kvo > 0] = 1
    k[kvo < 0] = -1
    
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
    return run_backtest(df, calc_osc_klinger, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
