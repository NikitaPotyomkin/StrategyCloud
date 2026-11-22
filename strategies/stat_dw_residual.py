"""Strategy: stat_dw_residual (H1).

Idea: Durbin-Watson residuals < 1.5 (trend) — тренд.
Вход: DW < 1.5 → тренд сигнал.
Выход: DW > 2.
Отличие: Durbin-Watson тест на autocorrelation residuals.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_dw_residual(df, period=20):
    """Durbin-Watson test on residuals.
    
    DW < 1.5 indicates trend.
    Signal in trend direction.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        x = np.arange(period, dtype=float)
        
        # OLS
        x_mean = np.mean(x)
        y_mean = np.mean(closes)
        
        slope = np.sum((x - x_mean) * (closes - y_mean)) / np.sum((x - x_mean)**2)
        intercept = y_mean - slope * x_mean
        
        # Residuals
        residuals = closes - (slope * x + intercept)
        
        # Durbin-Watson statistic
        diff_sq = np.sum(np.diff(residuals)**2)
        res_sq = np.sum(residuals**2)
        
        if res_sq > 0:
            dw = diff_sq / res_sq
            
            # DW < 1.5 → trend
            if dw < 1.5:
                if slope > 0:
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
    return run_backtest(df, calc_stat_dw_residual, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
