"""Strategy: ma_vidya_trend (H1).

Idea: VIDYA rising 3 bars — Variable Index Dynamic Average.
Вход: VIDYA восходящая 3 бара → long.
Выход: наклон < 0.
Отличие: VIDYA адаптирует период к волатильности.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_ma_vidya_trend(df, period=20):
    """VIDYA (Variable Index Dynamic Average) trend.
    
    VIDYA rising 3 bars → long signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Calculate VIDYA
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_mean = atr.rolling(20).mean().iloc[i]
        
        # VIDYA alpha
        er = abs(closes[-1] - closes[0]) / (atr_mean * period) if atr_mean > 0 else 0.5
        alpha = er * 0.8 + 0.2
        
        # VIDYA calculation
        vidya = closes[0]
        for j in range(1, len(closes)):
            vidya = alpha * closes[j] + (1 - alpha) * vidya
        
        # Check rising 3 bars
        if closes[-1] > closes[-2] > closes[-3]:
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
    return run_backtest(df, calc_ma_vidya_trend, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
