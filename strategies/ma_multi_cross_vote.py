"""MA: Multi-Cross Vote (H1).

Idea: 0270 ma_multi_cross_vote
Вход: 3 of 5 MA crosses agreed
Выход: 3 against
Отличие: Ensemble of 5 MAs with voting
"""
import numpy as np
import pandas as pd


def calc_ma_multi_cross_vote(df, period=5):
    ma5 = df['close'].rolling(period).mean()
    ma10 = df['close'].rolling(period*2).mean()
    ma20 = df['close'].rolling(period*4).mean()
    ma50 = df['close'].rolling(period*10).mean()
    ma100 = df['close'].rolling(period*20).mean()
    
    # БЫЛО: votes = 0 и `if df['close'] > ma5: votes += 1` — сравнение Series в
    # if бросало ValueError ("truth value of a Series is ambiguous"), то есть
    # calc падал на первом же вызове. Считаем голоса векторно.
    votes = np.zeros(len(df), dtype=int)
    votes += (df['close'] > ma5).to_numpy(dtype=int)
    votes += (df['close'] > ma10).to_numpy(dtype=int)
    votes += (df['close'] > ma20).to_numpy(dtype=int)
    votes += (df['close'] > ma50).to_numpy(dtype=int)
    votes += (df['close'] > ma100).to_numpy(dtype=int)
    
    k = np.zeros(len(df))
    k[votes >= 3] = 1
    k[votes <= 2] = -1
    
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
    return run_backtest(df, calc_ma_multi_cross_vote, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
