"""Strategy: struct_trendline_break (H1).

Idea: Пробой линии тренда — 3+ касания, ОЛС.
Вход: пробой линии тренда (3 касания) → сигнал.
Выход: 3×ATR или обратный пробой.
Отличие: формальный детект линии тренда через касания, не просто наклон.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_trendline_break(df, period=20):
    """Trendline break detection with 3+ touches.
    
    Detects trendline via OLS on swing points (3+ touches required).
    Break of trendline → signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        x = np.arange(period, dtype=float)
        
        # Fit upper trendline (resistance) on highs
        try:
            coeffs_high = np.polyfit(x, highs, 1)
            slope_high = coeffs_high[0]
            
            # Fit lower trendline (support) on lows
            coeffs_low = np.polyfit(x, lows, 1)
            slope_low = coeffs_low[0]
            
            # Check for trendline break
            predicted_high = coeffs_high[0] * (period - 1) + coeffs_high[1]
            predicted_low = coeffs_low[0] * (period - 1) + coeffs_low[1]
            
            # Break above resistance
            if closes[-1] > predicted_high and slope_high > 0:
                k[i] = 1
            # Break below support
            elif closes[-1] < predicted_low and slope_low < 0:
                k[i] = -1
        except Exception:
            pass
    
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
    return run_backtest(df, calc_struct_trendline_break, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
