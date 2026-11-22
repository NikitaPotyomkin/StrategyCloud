"""MA: Zero-Lag EMA (H1).

Idea: 0264 ma_zerolag
Вход: zero-lag EMA(16) crosses SMA(32)
Выход: reverse cross
Отличие: Zero-lag smoothing for faster signals
"""
import numpy as np
import pandas as pd


def calc_ma_zerolag(df, period=16):
    ema_period = period
    slow_period = period * 2
    
    ema = df['close'].ewm(span=ema_period).mean()
    sma = df['close'].rolling(slow_period).mean()
    
    # Zero-lag adjustment
    zlema = 2 * ema - ema.shift(ema_period // 2)
    
    k = np.zeros(len(df))
    k[zlema > sma] = 1
    k[zlema < sma] = -1
    
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
    return run_backtest(df, calc_ma_zerolag, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
