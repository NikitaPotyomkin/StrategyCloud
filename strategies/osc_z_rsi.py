"""Oscillator: Z-Score RSI (H1).

Idea: 0354 osc_z_of_rsi
Вход: z-score RSI(14) > 2
Выход: z < 0
Отличие: RSI normalized by rolling statistics
"""
import numpy as np
import pandas as pd


def calc_osc_z_rsi(df, period=100):
    gains = df['close'].diff().clip(lower=0)
    losses = -df['close'].diff().clip(upper=0)
    avg_gain = gains.rolling(14).mean()
    avg_loss = losses.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    
    rsi_mean = rsi.rolling(period).mean()
    rsi_std = rsi.rolling(period).std()
    z = (rsi - rsi_mean) / rsi_std.replace(0, np.nan)
    
    k = np.zeros(len(df))
    k[z > 2.0] = 1
    k[z < -2.0] = -1
    
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
    return run_backtest(df, calc_osc_z_rsi, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
