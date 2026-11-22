"""Strategy: struct_order_block (H1).

Idea: Order Block — возврат к последней бычьей/медвежьей свече перед импульсом.
Вход: цена возвращается к бычьему OB (последняя green перед big red) → long.
Выход: импульс high достигнут или OB пробит.
Отличие: OB — зона институционального интереса, не просто поддержка.

Правка 15.11.2026: SL/TP >= 10 спредов, горизонт 5-20 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_struct_order_block(df, period=20):
    """Order Block detection.
    
    Detects last bullish candle before bearish impulse (bullish OB)
    or last bearish candle before bullish impulse (bearish OB).
    """
    k = np.zeros(len(df))
    
    for i in range(period, len(df)):
        opens = df['open'].iloc[i-period:i].values
        closes = df['close'].iloc[i-period:i].values
        highs = df['high'].iloc[i-period:i].values
        lows = df['low'].iloc[i-period:i].values
        
        # Find bullish OB: green candle before big red drop
        for j in range(len(opens) - 3):
            if closes[j] > opens[j]:  # bullish candle
                # Check if next candles form bearish impulse
                impulse_strength = opens[j] - min(closes[j+1:j+4])
                if impulse_strength > 0.001:  # significant drop
                    # Check if price returns to OB zone
                    ob_high = highs[j]
                    ob_low = lows[j]
                    if closes[-1] >= ob_low and closes[-1] <= ob_high:
                        k[i] = 1
                        break
        
        if k[i] == 0:
            # Find bearish OB: red candle before big green rally
            for j in range(len(opens) - 3):
                if closes[j] < opens[j]:  # bearish candle
                    # Check if next candles form bullish impulse
                    impulse_strength = max(closes[j+1:j+4]) - opens[j]
                    if impulse_strength > 0.001:  # significant rally
                        # Check if price returns to OB zone
                        ob_high = highs[j]
                        ob_low = lows[j]
                        if closes[-1] >= ob_low and closes[-1] <= ob_high:
                            k[i] = -1
                            break
    
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
    return run_backtest(df, calc_struct_order_block, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
