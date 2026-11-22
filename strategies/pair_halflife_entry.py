"""Pairs: Half-Life Entry (H1).

Idea: 0571 pair_halflife_entry
Вход: spread z > 2 with half-life < 15 bars
Выход: z < 0
Отличие: Mean-reversion with half-life filter
"""
import numpy as np
import pandas as pd


def calc_pair_halflife_entry(df, period=200):
    ret = df['close'].pct_change()
    
    half_life = pd.Series(np.nan, index=df.index)
    
    for i in range(period, len(df)):
        y = ret.iloc[i-period:i]
        x = y.shift(1).dropna()
        y = y.iloc[1:].reset_index(drop=True)
        
        if x.empty or y.empty:
            continue
            
        try:
            theta = -(np.cov(x.values, y.values)[0, 1] / np.var(x.values))
            hl = np.log(2) / theta if theta > 0 else np.inf
            half_life.iloc[i] = hl
        except:
            continue
    
    z = (ret - ret.rolling(period).mean()) / ret.rolling(period).std().replace(0, np.nan)
    
    k = np.zeros(len(df))
    k[(half_life < 15) & (z > 2)] = 1
    k[(half_life < 15) & (z < -2)] = -1
    
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
    return run_backtest(df, calc_pair_halflife_entry, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
