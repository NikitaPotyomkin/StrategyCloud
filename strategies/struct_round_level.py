"""Strategy: struct_round_level (H1).

Idea: Отскок от круглого уровня (00/50) — психологические уровни.
Вход: цена подходит к круглому уровню и разворачивается → сигнал.
Выход: следующий круглый уровень или trail 1.5×ATR.
Отличие: круглые уровни — психологические зоны интереса рынка.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_round_level(df, period=20):
    """Round level detection and bounce.
    
    Detects price approaching round levels (ending in 00 or 50).
    Bounce from round level → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # Find nearest round level
        last_price = closes[-1]
        
        # Round to nearest 50
        round_level = round(last_price / 50) * 50
        
        # Distance to round level
        distance = abs(last_price - round_level)
        
        # If price is close to round level (< 0.1% of price)
        if distance < 0.001 * last_price:
            # Check for bounce
            if closes[-1] > lows[-1] and closes[-1] > closes[-2]:
                # Bounce from round level → long
                if last_price < round_level:
                    k[i] = 1
                # Reject from round level → short
                elif last_price > round_level:
                    k[i] = -1
        
        # Also check for break of round level
        if distance < 0.002 * last_price:
            if closes[-1] > round_level and closes[-2] <= round_level:
                k[i] = 1
            elif closes[-1] < round_level and closes[-2] >= round_level:
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
    return run_backtest(df, calc_struct_round_level, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
