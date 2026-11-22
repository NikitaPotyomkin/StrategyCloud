"""Volume: Volume Dry (H1).

Idea: 0097 volprof_volume_dry
Вход: vol < p20 for 5 bars, then > p70
Выход: 4 bars
Отличие: Volume exhaustion breakout
"""
import numpy as np
import pandas as pd


def calc_volprof_volume_dry(df, period=5):
    vol = df['volume'] if 'volume' in df.columns else pd.Series(1, index=df.index)
    p20 = vol.rolling(20).quantile(0.20)
    p70 = vol.rolling(20).quantile(0.70)
    
    dry = vol < p20
    dry_streak = dry.rolling(period).sum()
    
    k = np.zeros(len(df))
    k[(dry_streak >= period) & (vol > p70)] = 1
    k[(dry_streak >= period) & (vol < p20 * 0.5)] = -1
    
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
    return run_backtest(df, calc_volprof_volume_dry, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
