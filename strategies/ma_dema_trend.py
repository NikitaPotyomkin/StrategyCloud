"""Strategy: ma_dema_trend (H1).

Idea: DEMA rising, ADX > 20 — Double EMA trend.
Вход: DEMA восходящая, ADX > 20 → long.
Выход: наклон < 0.
Отличие: DEMA устраняет lag SMA удвоением сглаживания.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_ma_dema_trend(df, period=20):
    """DEMA (Double EMA) trend with ADX filter.
    
    DEMA rising and ADX > 20 → long signal.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # EMA calculation
        ema1 = np.mean(closes[-14:])
        ema2 = np.mean(closes[-28:]) if len(closes) >= 28 else ema1
        
        # DEMA = 2*EMA1 - EMA2
        dema = 2 * ema1 - ema2
        
        # ADX proxy (trend strength)
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_mean = atr.rolling(14).mean().iloc[i]
        trend_strength = abs(closes[-1] - closes[-2]) / atr_mean if atr_mean > 0 else 0
        
        # DEMA rising with ADX > 20 (proxy > 0.5)
        if dema > ema1 and trend_strength > 0.5:
            k[i] = 1
        elif dema < ema1 and trend_strength > 0.5:
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
    return run_backtest(df, calc_ma_dema_trend, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
