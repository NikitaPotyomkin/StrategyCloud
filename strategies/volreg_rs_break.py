"""Volatility Regime: Rogers-Satchell Break (H1).

Idea: 0003 volreg_rs_break
Вход: Rogers-Satchell > p90(120) и пробой high(20)
Выход: trail 2xATR
Отличие: RS-волатильность работает для трендовых рынков лучше чем GC
"""
import numpy as np
import pandas as pd


def calc_volreg_rs_break(df, period=20):
    """Rogers-Satchell volatility breakout."""
    o = np.log(df['open'])
    h = np.log(df['high'])
    l = np.log(df['low'])
    c = np.log(df['close'])
    
    # RS volatility
    rs_vol = (h - o) * (h - c) + (c - o) * (l - o)
    rs_vol = rs_vol.clip(lower=0)  # ensure non-negative
    
    rolling_mean = rs_vol.rolling(120).mean()
    rolling_std = rs_vol.rolling(120).std()
    p90 = rs_vol.rolling(120).quantile(0.90)
    
    high_20 = rs_vol.rolling(20).max()
    
    k = np.zeros(len(df))
    k[(rs_vol > p90) & (rs_vol > high_20)] = 1
    k[(rs_vol < rolling_mean - rolling_std)] = -1
    
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    if prev == 0 and curr == 1:
        return True
    if prev == 0 and curr == -1:
        return True
    return False


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


from strategies._bt_core import run_backtest
def _entry(prev, curr):
    """check_entry модуля отдаёт bool — направление берём из знака состояния.

    Прежняя петля входила в long при переходе 0→+1 и в short при 0→−1, а
    run_backtest ждёт 'long'/'short'/None. Булев ответ разворачиваем по curr.
    """
    if not check_entry(prev, curr):
        return None
    if curr == 1:
        return 'long'
    if curr == -1:
        return 'short'
    return None


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    """Симуляция через общий движок strategies/_bt_core.run_backtest.

    Вход по open следующего бара ± спред, спред вычитается и на выходе, обрыва
    по времени нет, деньги через trade_profit (÷ tick_size). Прежняя петля
    входила по close сигнального бара, не вычитала спред, выбрасывала сделки,
    не закрывшиеся за 49 баров, и считала P&L без деления на tick_size —
    из-за этого её числа были несравнимы с остальным реестром.
    """
    return run_backtest(df, calc_volreg_rs_break, _entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
