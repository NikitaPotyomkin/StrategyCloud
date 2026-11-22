"""Strategy: regime_range_classifier (H1).

Idea: "Range" classifier by 3 features (ER, ATR%, BBW) — классификатор.
Вход: range classifier → signal when 1 feature leaves.
Выход: when regime changes.
Отличие: multi-feature regime classification.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_regime_range_classifier(df, period=20):
    """Range classifier by 3 features.
    
    Range detected → signal when feature leaves.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        closes = df['close'].iloc[i-period:i].values
        
        # Feature 1: Efficiency Ratio (ER)
        er = abs(closes[-1] - closes[0]) / np.sum(np.abs(np.diff(closes)))
        
        # Feature 2: ATR%
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_pct = atr.rolling(20).mean().iloc[i] / closes[-1]
        
        # Feature 3: BBW
        bb_std = pd.Series(closes).rolling(20).std().iloc[-1]
        bbw = 2 * bb_std / np.mean(closes)
        
        # Range classifier (low ER, low ATR%, low BBW)
        if er < 0.3 and atr_pct < 0.02 and bbw < 0.1:
            # Breakout from range
            if closes[-1] > np.max(closes[:-1]):
                k[i] = 1
            elif closes[-1] < np.min(closes[:-1]):
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
    return run_backtest(df, calc_regime_range_classifier, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
