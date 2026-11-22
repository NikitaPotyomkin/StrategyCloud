"""Regime: ER Low (H1).

Idea: 0533 regime_er_low
Вход: ER < 0.2 (flat) → mean-reversion
Выход: ER > 0.35
Отличие: Kaufman Efficiency Ratio for flat detection
"""
import numpy as np
import pandas as pd


def calc_regime_er_low(df, period=20):
    change = abs(df['close'] - df['close'].shift(period))
    vol = df['close'].diff().abs().rolling(period).sum()
    er = change / vol.replace(0, np.nan)
    
    k = np.zeros(len(df))
    k[er < 0.2] = 1  # flat → mean-reversion
    k[er > 0.35] = -1  # trend → don't revert
    
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
    return run_backtest(df, calc_regime_er_low, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
