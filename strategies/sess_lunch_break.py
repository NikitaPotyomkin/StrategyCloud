"""Strategy: sess_lunch_break (H1).

Idea: Lunch low volatility 12:00-13:00 — breakout низкой волатильности.
Вход: диапазон 12:00-13:00 < p30 → пробой → сигнал.
Выход: 1.5× диапазон lunch.
Отличие: lunch breakout — классический intraday паттерн.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_sess_lunch_break(df, period=20):
    """Lunch low volatility breakout.
    
    Detects low volatility lunch period (12:00-13:00).
    Breakout from lunch range → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Use last 2 bars as lunch proxy
        lunch_high = np.max(highs[:2])
        lunch_low = np.min(lows[:2])
        lunch_range = lunch_high - lunch_low
        
        # Calculate average range
        avg_range = np.mean(highs[2:]) - np.mean(lows[2:])
        
        # Low volatility lunch (<0.5× average)
        if lunch_range < 0.5 * avg_range and avg_range > 0:
            # Breakout
            if closes[-1] > lunch_high:
                k[i] = 1
            elif closes[-1] < lunch_low:
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
    return run_backtest(df, calc_sess_lunch_break, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
