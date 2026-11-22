"""Strategy: ma_mcginley (H1).

Idea: McGinley Dynamic rising and price above — адаптивная средняя.
Вход: McGinley растёт и цена выше → long.
Выход: цена ниже McGinley.
Отличие: McGinley адаптируется к скорости рынка.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_ma_mcginley(df, period=20):
    """McGinley Dynamic trend.
    
    McGinley rising and price above → long.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Simple McGinley proxy
        md = np.mean(closes)
        
        # Calculate change
        if i > 1:
            prev_md = np.mean(closes[:-1])
            price_change = abs(closes[-1] - closes[-2])
            
            # Rising McGinley
            if md > prev_md and closes[-1] > md:
                k[i] = 1
    
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
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
    return run_backtest(df, calc_ma_mcginley, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
