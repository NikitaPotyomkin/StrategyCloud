"""Strategy: mr_keltner_pct (H1).

Idea: Beyond Keltner + BBW < p30 (flat) — возврат к середине.
Вход: цена вне Keltner + низкая BBW → fade к середине.
Выход: middle Keltner.
Отличие: комбинация Keltner + BBW для фильтра flat.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_mr_keltner_pct(df, period=20):
    """Mean reversion from Keltner with BBW filter.
    
    Price beyond Keltner + low BBW → fade to middle.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # Keltner middle (SMA)
        kelt_mid = np.mean(closes)
        
        # Keltner bandwidth (ATR-based)
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_mean = atr.rolling(20).mean().iloc[i]
        kelt_upper = kelt_mid + 2 * atr_mean
        kelt_lower = kelt_mid - 2 * atr_mean
        
        # BBW (Bollinger Band Width)
        bb_mid = pd.Series(closes).rolling(20).mean().iloc[i]
        bb_std = pd.Series(closes).rolling(20).std().iloc[i]
        bbw = 2 * bb_std / bb_mid if bb_mid > 0 else 0
        
        # Low BBW (< p30)
        if bbw < 0.05:  # proxy for low
            # Beyond Keltner
            if closes[-1] > kelt_upper:
                k[i] = -1
            elif closes[-1] < kelt_lower:
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
    return run_backtest(df, calc_mr_keltner_pct, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
