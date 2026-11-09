"""Volatility Regime: Vol-of-Vol (H1).

Idea: 0005 volreg_volofvol
Вход: vol-of-vol (std Parkinson(20) за period) выше своего p80 и close > open;
      ниже своего p20 и close < open — короткая сторона (симметрично).
Выход: смена состояния k (check_exit), плюс SL/TP.
Отличие: vol-of-vol detects volatility acceleration.

Правка 10.11.2026: раньше std(park) сравнивался с перцентилем САМОГО park
(уровень волатильности против её же разброса) — величины в разных единицах:
лонг почти никогда не срабатывал, шорт срабатывал почти на любом красном баре
в спокойном рынке. Теперь оба порога — перцентили ряда vol-of-vol.
Бэктест переведён на общий движок strategies._bt_core (вход по open следующего
бара, спред, выход по сигналу) — как у остальных семейств.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_volreg_volofvol(df, period=60):
    hl = np.log(df['high'] / df['low']) ** 2
    park = hl.rolling(20).mean() ** 0.5
    volofvol = park.rolling(period).std()
    hi = volofvol.rolling(period).quantile(0.80)
    lo = volofvol.rolling(period).quantile(0.20)

    k = np.zeros(len(df))
    k[(volofvol > hi) & (df['close'] > df['open'])] = 1
    k[(volofvol < lo) & (df['close'] < df['open'])] = -1

    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    return (prev == 0 and curr == 1) or (prev == 0 and curr == -1)


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    return run_backtest(df, calc_volreg_volofvol, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
