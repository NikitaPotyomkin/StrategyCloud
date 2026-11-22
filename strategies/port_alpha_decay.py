"""Portfolio Layer: Alpha Decay Monitor (H1).

Idea: 0968 port_alpha_decay
Вход: контроль затухания: живой IC ниже 0 -> выключить;
      выход: IC восстанавливается.
Отличие: alpha decay = стратегия теряет предсказательную силу со временем.

Правка 12.11.2026: Это фильтр, не входной сигнал.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_port_alpha_decay(df, period=100):
    ret = df['close'].pct_change().fillna(0)

    # Information Coefficient = корреляция signal vs return
    # Прокси: autocorrelation ret как прокси стабильности alpha

    # Rolling autocorrelation
    acf = ret.rolling(period).autocorr(1)
    acf = acf.fillna(0)

    # Alpha decay: ACF < 0 (отрицательная предсказуемость)
    is_decayed = acf < -0.1

    # После decay: пауза
    k = np.zeros(len(df))
    k[~is_decayed & (ret > 0)] = 1
    k[~is_decayed & (ret < 0)] = -1
    k[is_decayed] = 0  # Фильтр: не торговать при decay

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
    return run_backtest(df, calc_port_alpha_decay, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
