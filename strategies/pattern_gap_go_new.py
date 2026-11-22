"""Strategy: pattern_gap_go (H1).

Idea: Гэп с продолжением (Gap-and-Go) — пробой гэпа в направлении тренда.
Вход: гэп > 0.3×ATR + тренд недели в том же направлении → long/short.
Выход: ADR или закрытие гэпа.
Отличие: гэп как подтверждение импульса, не просто fade.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_pattern_gap_go(df, period=20):
    """Gap and Go pattern detection.
    
    Detects gap > 0.3×ATR with trend confirmation.
    Trade in gap direction with trend.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        opens = df['open'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # Calculate ATR
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_mean = atr.rolling(20).mean().iloc[i]
        
        # Detect gap (open vs previous close)
        if i > 0:
            prev_close = closes[-2]
            current_open = opens[-1]
            
            gap_size = abs(current_open - prev_close)
            
            # Gap > 0.3×ATR
            if gap_size > 0.3 * atr_mean:
                # Bullish gap
                if current_open > prev_close:
                    # Check trend (price above SMA50)
                    sma50 = df['close'].rolling(50).mean().iloc[i]
                    if closes[-1] > sma50:
                        k[i] = 1
                # Bearish gap
                elif current_open < prev_close:
                    # Check trend (price below SMA50)
                    sma50 = df['close'].rolling(50).mean().iloc[i]
                    if closes[-1] < sma50:
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
    return run_backtest(df, calc_pattern_gap_go, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
