"""Strategy: sess_night_range (H1).

Idea: Night range < p30 — пробой на открытии Азии.
Вход: ночной диапазон < p30 → пробой → 2× диапазон.
Выход: 2× ночной диапазон.
Отличие: узкий ночной диапазон предвещает движение.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_sess_night_range(df, period=20):
    """Night range breakout strategy.
    
    Detects narrow night range (<p30).
    Breakout on Asia open → signal with 2× range target.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Night range (first 4 bars as proxy)
        night_high = np.max(highs[:4])
        night_low = np.min(lows[:4])
        night_range = night_high - night_low
        
        # Calculate percentile of range
        all_ranges = []
        for j in range(max(0, i-100), i):
            if j + 4 < len(df):
                r = df['high'].iloc[j+4] - df['low'].iloc[j]
                all_ranges.append(r)
        
        if len(all_ranges) > 0:
            night_range_pct = np.mean([r < night_range for r in all_ranges])
            
            # Narrow range (<p30)
            if night_range_pct < 0.30:
                # Breakout
                if closes[-1] > night_high:
                    k[i] = 1
                elif closes[-1] < night_low:
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
    return run_backtest(df, calc_sess_night_range, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
