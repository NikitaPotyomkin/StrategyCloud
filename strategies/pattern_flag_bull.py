"""Pattern Flag Bull (H1).

Idea: Bull flag pattern - strong impulse up followed by shallow consolidation
Вход: impulse > p15% of price, then flag (consolidation) < 50% of impulse, then breakout
Выход: k flips from 1 to 0 (long) or -1 to 0 (short)
Отличие: Requires two-phase detection: impulse identification + flag consolidation
"""
import numpy as np
import pandas as pd


def calc_pattern_flag_bull(df, period=20):
    """Calculate signal. Returns df with 'k' column."""
    k = np.zeros(len(df))
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    # (right) Find impulse: significant move up over lookback
    impulse_mag = np.zeros(len(close))
    impulse_start = np.zeros(len(close))
    for i in range(period, len(close)):
        # (right) Find best impulse window within period
        best_imp = 0
        best_start = i
        for s in range(i - period + 1, i):
            imp = close[i] - close[s]
            if imp > best_imp:
                best_imp = imp
                best_start = s
        impulse_mag[i] = best_imp
        impulse_start[i] = best_start
    # (right) Detect flag: low volatility consolidation after impulse
    flag = np.zeros(len(close))
    for i in range(period, len(close)):
        if impulse_mag[i] > 0:
            # (right) Flag range: recent bars after impulse
            flag_start = int(impulse_start[i])
            flag_end = i
            flag_range = np.max(high[flag_start:flag_end]) - np.min(low[flag_start:flag_end])
            # (right) Flag should be less than 50% of impulse
            if flag_range < 0.5 * impulse_mag[i] and flag_range > 0:
                flag[i] = 1
    # (right) k=1: flag detected + close above flag high
    flag_high = np.zeros(len(close))
    for i in range(period, len(close)):
        if flag[i]:
            flag_start = int(impulse_start[i])
            flag_end = i
            flag_high[i] = np.max(high[flag_start:flag_end])
    # (right) convert to Series for .shift() compatibility
    flag_high_s = pd.Series(flag_high, index=df.index)
    k = np.where((flag == 1) & (df['close'] > flag_high_s.shift(1)), 1, k)
    # (right) k=-1: bear flag detected + close below flag low
    flag_low = np.zeros(len(close))
    for i in range(period, len(close)):
        if flag[i]:
            flag_start = int(impulse_start[i])
            flag_end = i
            flag_low[i] = np.min(low[flag_start:flag_end])
    # (right) convert to Series for .shift() compatibility
    flag_low_s = pd.Series(flag_low, index=df.index)
    k = np.where((flag == 1) & (df['close'] < flag_low_s.shift(1)), -1, k)
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
    return run_backtest(df, calc_pattern_flag_bull, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
