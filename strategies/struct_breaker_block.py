"""Strategy: struct_breaker_block (H1).

Idea: Breaker Block — пробой предыдущей зоны предложения/спроса.
Вход: пробой предыдущего swing high с импульсом → long; swing low → short.
Выход: 2×ATR или обратный пробой.
Отличие: BB — зона где "застряли" ордера, пробой высвобождает энергию.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_breaker_block(df, period=20):
    """Breaker Block detection.
    
    Detects breakout of previous supply/demand zone (breaker block).
    When price breaks above swing high with momentum → long.
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        volumes = df['volume'].iloc[i-period:i].values
        
        # Find swing high/low
        swing_high = max(highs[1:-1])
        swing_low = min(lows[1:-1])
        mid_high = (swing_high + min(highs[-5:])) / 2
        mid_low = (swing_low + max(lows[-5:])) / 2
        
        # Check volume confirmation
        vol_mean = np.mean(volumes)
        vol_confirm = volumes[-1] > 1.5 * vol_mean
        
        # Bullish BB: break above swing high with volume
        if closes[-1] > swing_high and vol_confirm:
            k[i] = 1
        # Bearish BB: break below swing low with volume
        elif closes[-1] < swing_low and vol_confirm:
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
    return run_backtest(df, calc_struct_breaker_block, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
