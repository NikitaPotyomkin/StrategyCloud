"""Pattern Triangle Sym (H1).

Idea: Symmetric triangle formed by converging highs and lows, trade breakout
Вход: highs decreasing and lows increasing over period, then close > upper or < lower
Выход: k flips from 1 to 0 (long) or -1 to 0 (short)
Отличие: Detects symmetric convergence pattern before breakout
"""
import numpy as np
import pandas as pd


def calc_pattern_triangle_sym(df, period=20):
    """Calculate signal. Returns df with 'k' column."""
    k = np.zeros(len(df))
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    # (right) Rolling max high and min low
    rolling_high = df['high'].rolling(period).max()
    rolling_low = df['low'].rolling(period).min()
    # (right) Check for converging pattern: highs decreasing, lows increasing
    # (right) Compare first half highs to second half highs
    is_converging = np.zeros(len(df), dtype=bool)
    for i in range(period, len(df)):
        window_high = high[i-period:i]
        window_low = low[i-period:i]
        # (right) Split into halves
        half = period // 2
        first_highs = window_high[:half]
        second_highs = window_high[half:]
        first_lows = window_low[:half]
        second_lows = window_low[half:]
        # (right) Highs decreasing, lows increasing
        if (np.mean(second_highs) < np.mean(first_highs) and
            np.mean(second_lows) > np.mean(first_lows)):
            is_converging[i] = True
    # (right) k=1: converging + close above rolling high
    k = np.where(is_converging & (close > rolling_high.shift(1)), 1, k)
    # (right) k=-1: converging + close below rolling low
    k = np.where(is_converging & (close < rolling_low.shift(1)), -1, k)
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
    return run_backtest(df, calc_pattern_triangle_sym, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
