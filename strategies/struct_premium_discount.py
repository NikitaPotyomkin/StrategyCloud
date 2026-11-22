"""Strategy: struct_premium_discount (H1).

Idea: Premium/Discount zone — цена в discount-зоне (ниже 50% свинга) + тренд → long.
Вход: цена ниже 50% свинга и EMA50 растёт → long; выше 50% и EMA50 падает → short.
Выход: цена достигает 50% midpoint.
Отличие: вход в направлении тренда по "выгодной" цене, как институционалы.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_premium_discount(df, period=20):
    """Premium/Discount zone detection with trend filter.
    
    Enters in trend direction when price is in discount (long) or premium (short) zone.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Calculate swing range
        swing_high = max(highs)
        swing_low = min(lows)
        swing_range = swing_high - swing_low
        
        if swing_range == 0:
            continue
        
        # 50% midpoint
        midpoint = swing_low + 0.5 * swing_range
        
        # EMA50 trend
        ema = df['close'].ewm(span=50, adjust=False).mean()
        ema_val = ema.iloc[i]
        ema_prev = ema.iloc[i-1] if i > 0 else ema_val
        ema_rising = ema_val > ema_prev
        
        # Discount zone: price below midpoint with uptrend
        if closes[-1] < midpoint and ema_rising:
            k[i] = 1
        # Premium zone: price above midpoint with downtrend
        elif closes[-1] > midpoint and not ema_rising:
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
    return run_backtest(df, calc_struct_premium_discount, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
