"""Volume: Effort vs Result (H1).

Idea: 0092 volprof_effort_result
Вход: effort (vol) rises, result (range) falls
Выход: 5 bars
Отличие: Volume-price effort/result divergence
"""
import numpy as np
import pandas as pd


def calc_volprof_effort_result(df, period=20):
    vol = df['volume'] if 'volume' in df.columns else pd.Series(1, index=df.index)
    range_ = df['high'] - df['low']
    
    # (right) rolling.sum() затем shift — shift нельзя применять к Rolling объекту
    vol_sum = vol.rolling(period).sum()
    range_sum = range_.rolling(period).sum()
    vol_trend = vol_sum - vol_sum.shift(1)
    range_trend = range_sum - range_sum.shift(1)
    
    k = np.zeros(len(df))
    k[(vol_trend > 0) & (range_trend < 0)] = 1
    k[(vol_trend < 0) & (range_trend > 0)] = -1
    
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
    return run_backtest(df, calc_volprof_effort_result, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
