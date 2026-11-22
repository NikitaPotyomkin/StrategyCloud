"""Volatility Regime: VHF Trend (H1).

Idea: 0012 volreg_vhf_trend
Вход: VHF(28) > 0.35 и цена выше SMA(50)
Выход: VHF < 0.2
Отличие: Vertical Horizontal Filter — высокий VHF = тренд, низкий = флэт
"""
import numpy as np
import pandas as pd


def calc_volreg_vhf_trend(df, period=28):
    """Vertical Horizontal Filter."""
    # (right) VHF = change / sum of absolute delta
    delta = df['close'].diff().abs()
    sum_delta = delta.rolling(period).sum()
    total_change = (df['close'] - df['close'].shift(period)).abs()

    vhf = total_change / (sum_delta + 1e-12)

    sma = df['close'].rolling(50).mean()

    k = np.zeros(len(df))
    k[(vhf > 0.35) & (df['close'] > sma)] = 1
    k[(vhf > 0.35) & (df['close'] < sma)] = -1

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
    return run_backtest(df, calc_volreg_vhf_trend, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
