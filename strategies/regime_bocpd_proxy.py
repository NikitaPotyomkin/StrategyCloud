"""Regime Detection: Bayesian Online Change-Point Proxy (H1).

Idea: 0523 regime_bocpd_proxy
Вход: байесовский онлайн change-point: вероятность смены режима > 0.8;
      вход по направлению нового режима (знак последнего бара).
Выход: вероятность смены режима < 0.3 (режим стабилизировался).
Отличие: BOCPD детектит структурные сдвиги в распределении ret.

Правка 12.11.2026: SL/TP ≥ 10 спредов, горизонт 5-15 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_regime_bocpd_proxy(df, period=100):
    """BOCPD proxy: change-point detection via rolling distribution shift.

    Используем KS-тест как прокси байесовского change-point:
    если распределение последних n баров статистически отличается
    от предыдущих window — вероятность смены режима > 0.8.
    """
    from scipy import stats

    ret = df['close'].pct_change().fillna(0)
    k = np.zeros(len(df))

    for i in range(period, len(df)):
        # Последние window баров vs предыдущие window баров
        recent = ret.iloc[i-period:i].values
        past = ret.iloc[i-2*period:i-period].values

        # KS-тест на различие распределений
        if len(recent) > 10 and len(past) > 10:
            try:
                ks_stat, ks_pval = stats.ks_2samp(recent, past)
                # p-value < 0.05 → распределения различаются → смена режима
                if ks_pval < 0.05 and ks_stat > 0.3:
                    # Вход по знаку последнего бара
                    if ret.iloc[i] > 0:
                        k[i] = 1
                    else:
                        k[i] = -1
            except Exception:
                pass

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
    return run_backtest(df, calc_regime_bocpd_proxy, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
