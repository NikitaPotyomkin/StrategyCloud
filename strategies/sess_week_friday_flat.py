"""Strategy: sess_week_friday_flat (H1).

Idea: Friday end-of-week reversal — разворот в конце пятницы.
Вход: цена далеко от open пятницы + конец дня → разворот к open.
Выход: open следующего дня.
Отличие: profit-taking на Friday close.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_sess_week_friday_flat(df, period=20):
    """Friday end-of-week reversal.
    
    Detects large Friday move from open.
    Reversal toward open at end of day.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        opens = df['open'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        
        # Distance from open
        distance = abs(closes[-1] - opens[-1])
        avg_distance = np.mean([abs(closes[j] - opens[j]) for j in range(len(opens))])
        
        # Large move (>1.5× average) at end of day
        if distance > 1.5 * avg_distance and avg_distance > 0:
            # Reversal: if price far above open → short (mean reversion)
            if closes[-1] > opens[-1]:
                k[i] = -1
            elif closes[-1] < opens[-1]:
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
    return run_backtest(df, calc_sess_week_friday_flat, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
