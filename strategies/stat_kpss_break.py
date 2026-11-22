"""Strategy: stat_kpss_break (H1).

Idea: KPSS test rejects stationarity around trend — тренд.
Вход: KPSS < 0.05 (тренд) → сигнал по знаку бара.
Выход: 1 день удержания.
Отличие: KPSS — тест на stationarity вокруг тренда.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_kpss_break(df, period=20):
    """KPSS test for trend detection.
    
    KPSS test rejects stationarity around trend (p<0.05).
    Signal in bar direction.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Simple KPSS proxy: test if series has trend
        x = np.arange(period, dtype=float)
        x_mean = np.mean(x)
        y_mean = np.mean(closes)
        
        # OLS slope
        slope = np.sum((x - x_mean) * (closes - y_mean)) / np.sum((x - x_mean)**2)
        
        # Residuals
        y_pred = slope * x + (y_mean - slope * x_mean)
        residuals = closes - y_pred
        
        # KPSS statistic proxy
        ss_tilde = np.cumsum(residuals - np.mean(residuals))**2
        kpss_stat = ss_tilde[-1] / np.sum(residuals**2)
        
        # If trend significant (kpss_stat > threshold)
        if kpss_stat > 0.5:
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
    return run_backtest(df, calc_stat_kpss_break, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
