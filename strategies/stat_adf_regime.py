"""Statistical Test: ADF Regime (H1).

Idea: 0481 stat_adf_regime
Вход: ADF p-value(120) < 0.05 (стационарность) -> mean-reversion;
      p > 0.3 (единичный корень) -> тренд.
Выход: p-value меняет режим.
Отличие: ADF-тест определяет стационарность vs тренд.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 8-24 бара.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_adf_regime(df, period=120):
    ret = df['close'].pct_change().fillna(0)

    # Простая аппроксимация ADF-теста через autocorrelation
    # ADF: проверяет H0: unit root (тренд) vs H1: stationary (mean-reversion)
    # Используем autocorrelation как прокси
    # .autocorr() doesn't take freq=, compute manually
    acf_1 = pd.Series(index=df.index, dtype=float)
    for i in range(period, len(df)):
        window = ret.iloc[i-period:i]
        if window.std() > 0:
            acf_1.iloc[i] = window.autocorr(lag=1)
        else:
            acf_1.iloc[i] = 0
    acf_1 = acf_1.fillna(0)

    # Низкая ACF(1) -> stationary (mean-reversion)
    # Высокая ACF(1) -> тренд
    acf_mean = acf_1.rolling(period).mean()
    acf_std = acf_1.rolling(period).std().replace(0, np.nan).fillna(1)

    acf_z = (acf_1 - acf_mean) / acf_std

    # Стационарность: ACF(1) < 0.5
    is_stationary = acf_1 < 0.5

    # Mean-reversion при стационарности
    k = np.zeros(len(df))
    k[is_stationary & (ret < 0)] = 1   # MR: long после падения
    k[is_stationary & (ret > 0)] = -1  # MR: short после роста

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
    return run_backtest(df, calc_stat_adf_regime, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
