"""Strategy: volprof_vol_shelf (H1).

Idea: Новый "этаж" объёма ниже текущей цены — volume shelf.
Вход: price near shelf → signal.
Выход: floor reached.
Отличие: volume shelf support/resistance.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_volprof_vol_shelf(df, period=20):
    """Volume shelf detection.
    
    New volume floor below current price → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        volumes = df['volume'].iloc[i-period:i].values
        
        # Find volume shelf (high volume node)
        shelf_idx = np.argmax(volumes)
        shelf_price = closes[shelf_idx]
        
        # Price above shelf
        if closes[-1] > shelf_price:
            # Approach to shelf
            if closes[-1] < shelf_price * 1.02:
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
    return run_backtest(df, calc_volprof_vol_shelf, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
