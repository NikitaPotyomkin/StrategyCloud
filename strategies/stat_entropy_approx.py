"""Stat Approx Entropy (H1).

Idea: Approximate Entropy < p30 indicates low complexity (trend-like) regime
Вход: ApEn < p30 with positive slope for long, negative for short
Выход: ApEn rises above p30 (complexity increases)
Отличие: Measures regularity in price series - low entropy = predictable trend
"""
import numpy as np
import pandas as pd


def _approx_entropy(series, m=2, r=None):
    """Calculate Approximate Entropy of a time series."""
    n = len(series)
    if n < m + 10:
        return 0.0

    if r is None:
        r = 0.2 * np.std(series)

    if r < 1e-12:
        return 0.0

    # Create embedded vectors
    def _count_matches(x, vecs, r):
        count = 0
        for v in vecs:
            max_diff = np.max(np.abs(np.array(x) - np.array(v)))
            if max_diff <= r:
                count += 1
        return count

    vecs_m = []
    for i in range(n - m):
        vecs_m.append(series[i:i + m])

    vecs_m1 = []
    for i in range(n - m - 1):
        vecs_m1.append(series[i:i + m + 1])

    # Count matches for dimension m
    B = np.zeros(n - m)
    for i in range(n - m):
        B[i] = _count_matches(vecs_m[i], vecs_m, r) / (n - m)

    # Count matches for dimension m+1
    A = np.zeros(n - m - 1)
    for i in range(n - m - 1):
        A[i] = _count_matches(vecs_m1[i], vecs_m1, r) / (n - m - 1)

    # Avoid log(0)
    B_avg = np.mean(B)
    A_avg = np.mean(A)

    if B_avg < 1e-10 or A_avg < 1e-10:
        return 0.0

    apen = -np.log(A_avg / B_avg)
    return apen


def calc_stat_entropy_approx(df, period=20):
    """Calculate approximate entropy signal. Returns df with 'k' column."""
    returns = np.diff(np.log(df['close'].values))
    n = len(df)
    k = np.zeros(n)

    # Store ApEn history for percentile tracking
    apen_history = []

    for i in range(period, n):
        window = returns[i - period:i]
        if len(window) < 20:
            continue

        apen = _approx_entropy(window, m=2, r=None)
        apen_history.append(apen)

        if len(apen_history) < 30:
            k[i] = 0
            continue

        sorted_apen = sorted(apen_history)
        p30_idx = int(0.3 * len(sorted_apen))
        p30_val = sorted_apen[min(p30_idx, len(sorted_apen) - 1)]

        if apen < p30_val:
            # Low complexity - check trend direction
            recent = returns[i - 5:i]
            slope = np.polyfit(np.arange(len(recent)), recent, 1)[0]
            if slope > 0:
                k[i] = 1
            elif slope < 0:
                k[i] = -1
            else:
                k[i] = 0
        else:
            k[i] = 0

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


from strategies._bt_core import run_backtest
def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    """Симуляция через общий движок strategies/_bt_core.run_backtest.

    Вход по open следующего бара ± спред, спред вычитается и на выходе, обрыва
    по времени нет, деньги через trade_profit (÷ tick_size). Прежняя петля
    входила по close сигнального бара, не вычитала спред, выбрасывала сделки,
    не закрывшиеся за 49 баров, и считала P&L без деления на tick_size —
    из-за этого её числа были несравнимы с остальным реестром.
    """
    return run_backtest(df, calc_stat_entropy_approx, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
