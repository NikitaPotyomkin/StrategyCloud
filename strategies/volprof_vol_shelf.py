"""Volume Profile: Vol Shelf (H1).

Idea: 0088 volprof_vol_shelf
Вход: объёмная "полка" — 3+ бара с объёмом в узком диапазоне (±15% от среднего)
     + пробой диапазона в сторону тренда.
Выход: объём разворачивается.
Отличие: обнаружение зон накопления/распределения по объёму.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 8-24 бара.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_volprof_vol_shelf(df, period=50, shelf_pct=0.15, min_bars=3):
    """Обнаружение "полки" объёма.
    
    Vol Shelf = серия баров с объёмом в узком диапазоне.
    Пробой полки в сторону тренда = сигнал.
    
    returns: df с колонкой 'k' (-1, 0, 1)
    """
    vol = df['volume'].values.astype(float)
    close = df['close'].values
    
    n = len(df)
    k = np.zeros(n)
    
    for i in range(period, n):
        # Скользящее среднее объёма
        vol_window = vol[i - period:i]
        vol_mean = vol_window.mean()
        
        if vol_mean <= 0:
            continue
        
        # Проверяем последние min_bars баров: все ли в диапазоне ±shelf_pct от среднего
        shelf_bars = min_bars
        is_shelf = True
        
        for j in range(1, shelf_bars + 1):
            vol_curr = vol[i - j]
            if vol_curr == 0 or abs(vol_curr - vol_mean) / vol_mean > shelf_pct:
                is_shelf = False
                break
        
        if not is_shelf:
            continue
        
        # Полка обнаружена — проверяем пробой
        # Цена должна выйти за пределы диапазона последних shelf_bars баров
        high_range = df['high'].iloc[i - shelf_bars:i].max()
        low_range = df['low'].iloc[i - shelf_bars:i].min()
        curr_high = df['high'].iloc[i]
        curr_low = df['low'].iloc[i]
        
        # Определяем тренд по средней цене
        ma_trend = df['close'].iloc[i - period:i].mean()
        curr_close = close[i]
        
        # Пробой вверх + тренд вверх = long
        if curr_high > high_range and curr_close > ma_trend:
            k[i] = 1
        # Пробой вниз + тренд вниз = short
        elif curr_low < low_range and curr_close < ma_trend:
            k[i] = -1
    
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Returns 'long' / 'short' / None for engine run_backtest
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
    return run_backtest(df, calc_volprof_vol_shelf, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
