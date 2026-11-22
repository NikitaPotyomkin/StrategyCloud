"""Strategy: chan_regression_band_z (H1).

Idea: Остаток регрессии z > 2 и наклон > 0 — регрессионный канал.
Вход: z > 2 → signal.
Выход: z < 0.
Отличие: regression band z-score.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_chan_regression_band_z(df, period=20):
    """Regression band z-score.
    
    Residual z > 2 → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        x = np.arange(period, dtype=float)
        
        # OLS regression
        x_mean = np.mean(x)
        y_mean = np.mean(closes)
        
        slope = np.sum((x - x_mean) * (closes - y_mean)) / np.sum((x - x_mean)**2)
        intercept = y_mean - slope * x_mean
        
        # Predicted
        predicted = slope * x + intercept
        
        # Residuals
        residuals = closes - predicted
        
        # Z-score
        z = residuals[-1] / np.std(residuals) if np.std(residuals) > 0 else 0
        
        # Signal
        if abs(z) > 2.0:
            if z > 0 and slope > 0:
                k[i] = 1
            elif z < 0 and slope < 0:
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
    return run_backtest(df, calc_chan_regression_band_z, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
