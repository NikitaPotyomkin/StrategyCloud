"""Volatility Regime: Garman-Klass Z-Score (H1).

Idea: 0002 volreg_gk_zscore
Вход: Garman-Klass z > 2
Выход: VWAP дня или 8 баров
Отличие: GK-волатильность (open/close/high/low), более точная чем ATR
"""
import numpy as np
import pandas as pd


def calc_volreg_gk_zscore(df, period=20):
    """Расчёт Garman-Klass volatility z-score."""
    # GK volatility estimator
    a = np.log(df['high'] / df['low']) ** 2
    b = np.log(df['close'] / df['open']) ** 2
    gk_vol = 0.5 * a - (2.0 * np.log(2) - 1) * b
    
    rolling_mean = gk_vol.rolling(period).mean()
    rolling_std = gk_vol.rolling(period).std()
    z = (gk_vol - rolling_mean) / rolling_std.replace(0, np.nan)
    
    k = np.zeros(len(df))
    k[z > 2.0] = 1
    k[z < -2.0] = -1
    
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
    return run_backtest(df, calc_volreg_gk_zscore, _entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
