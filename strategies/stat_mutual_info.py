"""Stat Mutual Info (H1).

Idea: Mutual information between return and volatility > p80 threshold
Вход: MI(ret, vol) > p80 for long, MI(ret, vol) < p20 for short
Выход: MI returns to median range [p20, p80]
Отличие: Nonlinear dependency between return direction and volatility magnitude
"""
import numpy as np
import pandas as pd


def _bin_values(values, n_bins=10):
    """Bin continuous values into discrete categories."""
    cleaned = values[~np.isnan(values)]
    if len(cleaned) < n_bins:
        return np.zeros(len(values))
    edges = np.percentile(cleaned, np.linspace(0, 100, n_bins + 1))
    edges = np.unique(edges)
    if len(edges) < 2:
        return np.zeros(len(values))
    binned = np.digitize(values, edges[1:-1]) - 1
    binned = np.clip(binned, 0, len(edges) - 2)
    return binned


def _mutual_info(x, y, n_bins=10):
    """Calculate mutual information between two variables."""
    bx = _bin_values(x, n_bins)
    by = _bin_values(y, n_bins)

    n = len(bx)
    if n < 10:
        return 0.0

    # Joint histogram
    joint = np.zeros((n_bins, n_bins))
    for i in range(n):
        joint[bx[i], by[i]] += 1

    joint = joint / n
    px = np.sum(joint, axis=1)
    py = np.sum(joint, axis=0)

    mi = 0.0
    for i in range(n_bins):
        for j in range(n_bins):
            if joint[i, j] > 0 and px[i] > 0 and py[j] > 0:
                mi += joint[i, j] * np.log(joint[i, j] / (px[i] * py[j]))

    return mi


def calc_stat_mutual_info(df, period=20):
    """Calculate mutual information signal. Returns df with 'k' column."""
    returns = np.diff(np.log(df['close'].values))
    abs_ret = np.abs(returns)

    # Volatility as rolling std of returns
    vol = pd.Series(returns).rolling(window=period, min_periods=5).std().values
    n = len(df)
    k = np.zeros(n)

    # Store MI values for percentile tracking
    mi_history = []

    for i in range(period, n):
        ret_window = returns[i - period:i]
        vol_window = vol[i - period:i]

        if np.all(np.isnan(vol_window)):
            continue

        mi = _mutual_info(ret_window, vol_window, n_bins=8)
        mi_history.append(mi)

        if len(mi_history) < 30:
            k[i] = 0
            continue

        # Calculate percentiles dynamically
        sorted_mi = sorted(mi_history)
        p80_idx = int(0.8 * len(sorted_mi))
        p20_idx = int(0.2 * len(sorted_mi))
        p80_val = sorted_mi[min(p80_idx, len(sorted_mi) - 1)]
        p20_val = sorted_mi[min(p20_idx, len(sorted_mi) - 1)]

        if mi > p80_val:
            k[i] = 1
        elif mi < p20_val:
            k[i] = -1
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
    return run_backtest(df, calc_stat_mutual_info, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
