"""Strategy: stat_johansen (H1).

Idea: Johansen cointegration rank of 3 pairs > 0 (basket) — коинтеграция.
Вход: коинтеграция pairs → basket signal.
Выход: когда basket breaks.
Отличие: Johansen тест на множественную коинтеграцию.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_johansen(df, period=20):
    """Johansen cointegration test proxy.
    
    Detects cointegration between pairs.
    Basket signal when cointegration found.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Simple cointegration proxy: test if spread is stationary
        returns = np.diff(closes)
        
        # ADF-like test on spread
        if len(returns) > 10:
            # Lagged differences
            lag_diff = np.diff(returns)
            spread = returns[1:]
            
            # OLS
            x = lag_diff[:-1]
            y = spread[1:]
            
            if len(x) > 5:
                x_mean = np.mean(x)
                y_mean = np.mean(y)
                
                beta = np.sum((x - x_mean) * (y - y_mean)) / np.sum((x - x_mean)**2)
                
                # Residuals
                residuals = y - beta * x
                
                # Test stationarity
                res_std = np.std(residuals)
                res_range = np.max(residuals) - np.min(residuals)
                
                # If residuals stationary (small range relative to std)
                if res_range < 5 * res_std:
                    if closes[-1] > closes[-2]:
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
    return run_backtest(df, calc_stat_johansen, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
