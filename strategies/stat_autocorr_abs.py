"""Statistical Test: Autocorrelation Clusters (H1).

Idea: 0501 stat_autocorr_abs
Вход: ACF(|ret|, 1) > 0.2 (кластеры волатильности);
      выход: ACF < 0.05.
Отличие: автокорреляция абсолютных ret детектит кластеризацию волатильности.

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 20-50 баров.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_stat_autocorr_abs(df, period=200):
    ret = df['close'].pct_change().fillna(0).abs()

    # ACF(1) абсолютных ret
    acf_values = [0.0] * (period - 1)
    for i in range(period - 1, len(df)):
        series = ret.iloc[i-period+1:i+1].values
        n = len(series)
        if n < 3:
            acf_values.append(0.0)
            continue
        mean = np.mean(series)
        var = np.var(series)
        if var > 0:
            # ACF(1)
            cov = np.mean((series[:-1] - mean) * (series[1:] - mean))
            acf = cov / var
            acf_values.append(acf)
        else:
            acf_values.append(0.0)

    # Вход по направлению текущего ret
    k = np.zeros(len(df))
    curr_ret = df['close'].pct_change().fillna(0)

    for i in range(len(df)):
        if i < len(acf_values) and acf_values[i] > 0.2:
            if curr_ret.iloc[i] > 0:
                k[i] = 1
            elif curr_ret.iloc[i] < 0:
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
    return run_backtest(df, calc_stat_autocorr_abs, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
