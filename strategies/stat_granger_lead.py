"""Strategy: stat_granger_lead (H1).

Idea: Granger: asset A leads B (lag 1-3) — лаговая связь.
Вход: A leads B → signal.
Выход: когда lag disappears.
Отличие: Granger causality тест на lead-lag.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_granger_lead(df, period=20):
    """Granger causality proxy.
    
    Detects lead-lag relationship.
    Signal when lead confirmed.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Simple Granger proxy: test if lagged returns predict current
        returns = np.diff(closes)
        
        if len(returns) > 5:
            # Lag 1
            lag1 = returns[:-1]
            current = returns[1:]
            
            # Correlation
            corr = np.corrcoef(lag1, current)[0, 1]
            
            # If lagged return predicts current
            if abs(corr) > 0.3:
                if corr > 0 and returns[-1] > 0:
                    k[i] = 1
                elif corr < 0 and returns[-1] < 0:
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
    return run_backtest(df, calc_stat_granger_lead, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
