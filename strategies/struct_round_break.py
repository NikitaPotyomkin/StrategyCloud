"""Strategy: struct_round_break (H1).

Idea: Пробой круглого уровня с объёмом — round level break.
Вход: round level break + volume → signal.
Выход: next round level.
Отличие: round level breakout with volume confirmation.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_round_break(df, period=20):
    """Round level breakout with volume.
    
    Round level break + volume → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        volumes = df['volume'].iloc[i-period:i].values
        
        # Round level
        last_price = closes[-1]
        round_level = round(last_price / 50) * 50
        
        # Distance to round level
        distance = abs(last_price - round_level)
        
        # Volume confirmation
        vol_mean = np.mean(volumes)
        vol_confirm = volumes[-1] > 1.5 * vol_mean
        
        # Breakout
        if distance < 0.001 * last_price and vol_confirm:
            if last_price > round_level:
                k[i] = 1
            elif last_price < round_level:
                k[i] = -1
    
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
    return run_backtest(df, calc_struct_round_break, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
