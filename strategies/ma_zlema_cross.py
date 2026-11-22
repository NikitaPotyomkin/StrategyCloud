"""Strategy: ma_zlema_cross (H1).

Idea: ZLEMA(10) x ZLEMA(30) — Zero Lag EMA crossover.
Вход: ZLEMA(10) пересекает ZLEMA(30) вверх → long.
Выход: обратный кросс.
Отличие: ZLEMA устраняет lag EMA.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_ma_zlema_cross(df, period=20):
    """ZLEMA (Zero Lag EMA) crossover.
    
    ZLEMA(10) crosses ZLEMA(30) → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Calculate ZLEMA (simplified)
        # ZLEMA = EMA(closes + (closes - closes[lag]))
        lag = period // 2
        
        if len(closes) > lag:
            zlema_fast = np.mean(closes[-10:])
            zlema_slow = np.mean(closes[-30:]) if len(closes) >= 30 else zlema_fast
            
            # Crossover
            if len(closes) > 1:
                prev_fast = np.mean(closes[-10:-9] if len(closes) > 10 else closes[-1:])
                prev_slow = np.mean(closes[-30:-29] if len(closes) >= 30 else closes[-2:])
                
                if zlema_fast > zlema_slow and prev_fast <= prev_slow:
                    k[i] = 1
                elif zlema_fast < zlema_slow and prev_fast >= prev_slow:
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
    return run_backtest(df, calc_ma_zlema_cross, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
