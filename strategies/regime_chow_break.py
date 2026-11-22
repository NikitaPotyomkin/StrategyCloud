"""Strategy: regime_chow_break (H1).

Idea: Chow test on two windows significant for slope — тест Чау.
Вход: slope change significant → signal.
Выход: 20 баров.
Отличие: Chow test structural break.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_regime_chow_break(df, period=20):
    """Chow test structural break.
    
    Slope change significant → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        x = np.arange(period, dtype=float)
        
        # Split into two windows
        mid = len(closes) // 2
        
        # OLS for both windows
        x1 = x[:mid]
        y1 = closes[:mid]
        x2 = x[mid:]
        y2 = closes[mid:]
        
        # Slope 1
        slope1 = np.sum((x1 - np.mean(x1)) * (y1 - np.mean(y1))) / np.sum((x1 - np.mean(x1))**2)
        
        # Slope 2
        slope2 = np.sum((x2 - np.mean(x2)) * (y2 - np.mean(y2))) / np.sum((x2 - np.mean(x2))**2)
        
        # Slope change
        slope_change = abs(slope2 - slope1)
        
        # Significant change
        if slope_change > 0.5:
            if slope2 > slope1:
                k[i] = 1
            else:
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
    return run_backtest(df, calc_regime_chow_break, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
