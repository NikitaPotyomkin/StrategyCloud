"""Chan Donchian Pct Squeeze (H1).

Idea: Donchian channel width contracts below threshold, then price breaks out
Вход: width_pct < p15 then close > upper band (long) or close < lower band (short)
Выход: k flips from 1 to 0 (long) or -1 to 0 (short)
Отличие: Entry on breakout bar after squeeze confirmed, width measured as percentage
"""
import numpy as np
import pandas as pd


def calc_chan_donchian_pct_squeeze(df, period=20):
    """Calculate signal. Returns df with 'k' column."""
    k = np.zeros(len(df))
    upper = df['high'].rolling(period).max()
    lower = df['low'].rolling(period).min()
    mid = (upper + lower) / 2.0
    # (right) width as percentage of mid
    width = (upper - lower) / mid
    # (right) squeeze condition: width below percentile threshold
    # (right) removed: p15 = int(df['param_key']) — param_key is not a df column, would raise KeyError
    width_pct = width.rolling(100).quantile(0.15) if len(width) > 100 else width.quantile(0.15)
    squeeze = width < width_pct
    # (right) k=1: squeeze + close above upper
    k = np.where(squeeze & (df['close'] > upper.shift(1)), 1, k)
    # (right) k=-1: squeeze + close below lower
    k = np.where(squeeze & (df['close'] < lower.shift(1)), -1, k)
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Возвращает 'long' / 'short' / None для engine run_backtest
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
    return run_backtest(df, calc_chan_donchian_pct_squeeze, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
