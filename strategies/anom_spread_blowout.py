"""Anomaly Detection: Spread Blowout (H1).

Idea: 0924 anom_spread_blowout
Вход: спред > 5×медианы -> пауза (фильтр, не вход);
      после нормализации спреда -> вход по направлению тренда.
Выход: спред возвращается к норме или trail 2×ATR.
Отличие: spread blowout = временное расширение спреда (проблемы с ликвидностью).

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 4-12 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_anom_spread_blowout(df, period=100):
    # Спред как range бара (proxy)
    spread_proxy = (df['high'] - df['low']) / df['close']

    # Медиана спреда
    spread_median = spread_proxy.rolling(period).median()

    # Значение спреда
    spread_val = spread_proxy / spread_median.replace(0, np.nan).fillna(1)

    # Spread blowout: > 5× медианы
    is_blowout = spread_val > 5.0

    # После blowout: вход по тренду EMA(50)
    ema_trend = df['close'].ewm(span=50, adjust=False).mean()

    k = np.zeros(len(df))

    # После blowout (следующие 3 бара)
    for i in range(len(df)):
        if is_blowout.iloc[i]:
            for j in range(1, 4):
                if i + j < len(df):
                    if df['close'].iloc[i+j] > ema_trend.iloc[i+j]:
                        k[i+j] = 1
                    elif df['close'].iloc[i+j] < ema_trend.iloc[i+j]:
                        k[i+j] = -1

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
    return run_backtest(df, calc_anom_spread_blowout, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
