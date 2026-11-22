"""Session: London Transition (H1).

Idea: 0361 sess_transition_ldn
Вход: открытие Лондона пробивает диапазон 08:00-09:00;
      выход: 1.5× диапазона.
Отличие: London open часто задаёт направление дня.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 4-12 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_sess_transition_ldn(df, period=20):
    # Прокси сессии: первые 2 бара дня = азия, след 2 = лондон
    # Используем rolling range как прокси сессионного диапазона

    high_session = df['high'].rolling(2).max()
    low_session = df['low'].rolling(2).min()
    session_range = high_session - low_session

    # Пробой сессионного диапазона
    breakout_up = df['close'] > high_session.shift(1)
    breakout_down = df['close'] < low_session.shift(1)

    # Объём подтверждает
    vol_mean = df['volume'].rolling(period).mean()
    high_vol = df['volume'] > vol_mean

    k = np.zeros(len(df))
    k[breakout_up & high_vol] = 1
    k[breakout_down & high_vol] = -1

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
    return run_backtest(df, calc_sess_transition_ldn, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
