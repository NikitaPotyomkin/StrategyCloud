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
    acf_values = []
    for i in range(period, len(df)):
        series = ret.iloc[i-period:i].values
        mean = np.mean(series)
        var = np.var(series)
        if var > 0:
            # ACF(1)
            cov = np.mean((series[:-1] - mean) * (series[1:] - mean))
            acf = cov / var
            acf_values.append(acf)
        else:
            acf_values.append(0)

    acf_series = pd.Series(acf_values, index=df.index[period-1:])
    acf_series = acf_series.reindex(df.index).fillna(0)

    # Кластеры: ACF > 0.2
    has_clusters = acf_series > 0.2

    # Вход по направлению текущего ret
    k = np.zeros(len(df))
    curr_ret = df['close'].pct_change().fillna(0)
    k[has_clusters & (curr_ret > 0)] = 1
    k[has_clusters & (curr_ret < 0)] = -1

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
