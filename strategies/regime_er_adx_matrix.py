"""Regime: ER-ADX Matrix (H1).

Idea: 0532 regime_er_adx_matrix
Вход: ER > 0.4 and ADX > 25 → trend
Выход: ER < 0.2
Отличие: Kaufman ER + ADX regime filter
"""
import numpy as np
import pandas as pd


def calc_regime_er_adx_matrix(df, period=20):
    change = abs(df['close'] - df['close'].shift(period))
    vol = df['close'].diff().abs().rolling(period).sum()
    er = change / vol.replace(0, np.nan)
    
    tr = np.maximum(df['high'] - df['low'], np.abs(df['high'] - df['close'].shift(1)))
    atr = tr.rolling(14).mean()
    dm_plus = np.maximum(df['high'].diff(), 0)
    dm_minus = np.maximum(-df['low'].diff(), 0)
    di_plus = 100 * dm_plus / atr
    di_minus = 100 * dm_minus / atr
    dx = 100 * np.abs(di_plus - di_minus) / (di_plus + di_minus).replace(0, np.nan)
    adx = dx.rolling(14).mean()
    
    k = np.zeros(len(df))
    k[(er > 0.4) & (adx > 25)] = 1
    k[(er < 0.2) | ((di_plus < di_minus) & (adx < 20))] = -1
    
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
    return run_backtest(df, calc_regime_er_adx_matrix, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
