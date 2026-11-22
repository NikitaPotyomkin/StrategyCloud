"""Oscillator: Aroon (H1).

Idea: 0350 osc_aroon_osc
Вход: Aroon Oscillator > 50
Выход: < 0
Отличие: Trend vs reversal detection
"""
import numpy as np
import pandas as pd


def calc_osc_aroon(df, period=25):
    high_25 = df['high'].rolling(period).max()
    low_25 = df['low'].rolling(period).min()
    
    # (right) rolling.apply с lambda и .index ломается на numpy arrays —
    # переписываем через explicit loop, возвращая float
    def _last_max_idx(arr):
        """Индекс последнего максимума в массиве."""
        if len(arr) == 0:
            return 0.0
        max_val = np.max(arr)
        # Ищем последний индекс максимума
        indices = np.where(arr == max_val)[0]
        return float(len(arr) - 1 - indices[-1])
    
    def _last_min_idx(arr):
        """Индекс последнего минимума в массиве."""
        if len(arr) == 0:
            return 0.0
        min_val = np.min(arr)
        indices = np.where(arr == min_val)[0]
        return float(len(arr) - 1 - indices[-1])
    
    periods_since_high = df['high'].rolling(period).apply(_last_max_idx, raw=True)
    periods_since_low = df['low'].rolling(period).apply(_last_min_idx, raw=True)
    
    aroon_up = periods_since_high / period * 100
    aroon_down = periods_since_low / period * 100
    osc = aroon_up - aroon_down
    
    k = np.zeros(len(df))
    k[osc > 50] = 1
    k[osc < 0] = -1
    
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
    return run_backtest(df, calc_osc_aroon, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
