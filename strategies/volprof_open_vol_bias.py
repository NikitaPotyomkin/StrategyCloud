"""Volume Profile: Open Vol Bias (H1).

Idea: 0089 volprof_open_vol_bias
Вход: сравнение объёма первых N баров сессии со средним.
     Если первые N баров имеют объём > 150% от среднего → bias в сторону тренда.
Выход: объём возвращается к среднему.
Отличие: обнаружение инициативных покупателей/продавцов в начале сессии.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 8-24 бара.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_volprof_open_vol_bias(df, period=50, open_bars=4, bias_ratio=1.5):
    """Обнаружение bias объёма в открытии сессии.
    
    Если первые N баров сессии имеют объём значительно выше среднего,
    это указывает на инициативный поток. Направление bias = направление цены.
    
    returns: df с колонкой 'k' (-1, 0, 1)
    """
    volume = df['volume'].values.astype(float)
    close = df['close'].values
    n = len(df)
    
    k = np.zeros(n)
    
    for i in range(period + open_bars, n):
        # Средний объём за последние period баров (без open_bars)
        vol_avg = volume[i - period - open_bars:i - open_bars].mean()
        
        if vol_avg <= 0:
            continue
        
        # Объёмы первых open_bars баров текущей window
        vol_open = volume[i - open_bars:i]
        avg_open_vol = vol_open.mean()
        
        # Первые бары имеют аномально высокий объём
        if avg_open_vol < bias_ratio * vol_avg:
            continue
        
        # Определяем направление bias по цене первых баров
        open_price = close[i - open_bars]
        curr_price = close[i]
        
        if curr_price > open_price:
            k[i] = 1   # Long bias
        elif curr_price < open_price:
            k[i] = -1  # Short bias
    
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


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    return run_backtest(df, calc_volprof_open_vol_bias, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
