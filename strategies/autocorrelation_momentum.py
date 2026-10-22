"""Стратегия Autocorrelation momentum — вход при ACF(1) > порога, выход при падении."""
import numpy as np
import pandas as pd

try:
    from numpy.lib.stride_tricks import sliding_window_view
except ImportError:  # numpy < 1.20
    def sliding_window_view(a, w):
        shape = (a.size - w + 1, w)
        strides = (a.strides[0], a.strides[0])
        return np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)


def calc_autocorrelation(df, acf_lag, vol_period=20):
    """
    Добавляет колонку 'acf' с автокорреляцией лага 1.

    Args:
        df: DataFrame с OHLCV
        acf_lag: лаг для расчёта автокорреляции
        vol_period: период для расчёта объёма

    Returns:
        DataFrame с колонкой 'acf'
    """
    df = df.copy()
    returns = df['close'].pct_change()

    # ── Автокорреляция (векторно, без цикла по барам) ──
    # Старый код брал окно x = returns[i-k : i+1] (k+1 значений, индексы i-k..i),
    # затем num = ((x-μ) * (x.shift(k)-μ)).sum(). shift(k) оставляет в окне только
    # один валидный сдвинутый элемент (позиция k = x[0]), поэтому num сводится к
    # (x[k]-μ)·(x[0]-μ). den = Σ(x-μ)^2; при den == 0 → 0. Для i < k+1 → 0.
    r = returns.to_numpy(dtype=float)
    n = len(r)
    k = int(acf_lag)
    acf_values = np.zeros(n, dtype=float)

    if k >= 0 and n > k + 1:
        windows = sliding_window_view(r, k + 1)     # строки s: r[s : s+k+1]
        chunk = max(1, 2_000_000 // (k + 1))
        s_last = n - k                               # s = 1 .. n-1-k  → i = s+k = k+1 .. n-1
        for start in range(1, s_last, chunk):
            stop = min(start + chunk, s_last)
            block = windows[start:stop]
            m = block.mean(axis=1)
            d = block - m[:, None]
            den = (d * d).sum(axis=1)
            num = d[:, k] * d[:, 0]
            with np.errstate(divide='ignore', invalid='ignore'):
                acf = num / den
            acf_values[start + k:stop + k] = np.where(den == 0, 0.0, acf)

    df['acf'] = acf_values
    return df


def check_entry(prev_acf, curr_acf, threshold):
    """
    Вход при росте автокорреляции выше порога.

    Returns:
        'long' или 'short' или None
    """
    # Рост ACF выше порога → продолжение тренда
    if prev_acf <= threshold and curr_acf > threshold:
        return 'long'
    # Падение ACF ниже порога → выход
    if prev_acf >= -threshold and curr_acf < -threshold:
        return 'short'
    return None


def check_exit(prev_acf, curr_acf, threshold, direction):
    """
    Выход при падении ACF ниже порога.

    Args:
        direction: 'long' или 'short'

    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_acf < threshold * 0.5
    else:
        return curr_acf > -threshold * 0.5


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, acf_lag, threshold, sl_points, tp_points, point,
             tick_value, tick_size, vol_period=20, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Autocorrelation momentum.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_autocorrelation(df, acf_lag, vol_period)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    from strategies._bt_core import TradeList, trade_row  # v2: журнал сделок
    trade_profits = TradeList()

    _c_acf = df['acf'].to_numpy()   # numpy-петля: позиционный доступ
    _c_close = df['close'].to_numpy()   # numpy-петля: позиционный доступ
    _c_high = df['high'].to_numpy()   # numpy-петля: позиционный доступ
    _c_low = df['low'].to_numpy()   # numpy-петля: позиционный доступ
    for i in range(1, len(df)):
        prev_acf = _c_acf[i - 1]
        curr_acf = _c_acf[i]
        curr_close = _c_close[i]
        current_high = _c_high[i]
        current_low = _c_low[i]

        # ── Проверка выхода ──
        if position:
            exited = False
            p = 0.0
            d = position['direction']

            if d == 'long':
                if current_low <= position['sl']:
                    p = _profit(position['entry'], position['sl'],
                                tick_value, tick_size, sim_lot, 'long')
                    exited = True
                elif current_high >= position['tp']:
                    p = _profit(position['entry'], position['tp'],
                                tick_value, tick_size, sim_lot, 'long')
                    exited = True
                elif check_exit(prev_acf, curr_acf, threshold, 'long'):
                    p = _profit(position['entry'], curr_close,
                                tick_value, tick_size, sim_lot, 'long')
                    exited = True
            else:
                if current_high >= position['sl']:
                    p = _profit(position['entry'], position['sl'],
                                tick_value, tick_size, sim_lot, 'short')
                    exited = True
                elif current_low <= position['tp']:
                    p = _profit(position['entry'], position['tp'],
                                tick_value, tick_size, sim_lot, 'short')
                    exited = True
                elif check_exit(prev_acf, curr_acf, threshold, 'short'):
                    p = _profit(position['entry'], curr_close,
                                tick_value, tick_size, sim_lot, 'short')
                    exited = True

            if exited:
                p -= (spread / tick_size) * tick_value * sim_lot
                profit += p
                n_trades += 1
                trade_profits.append(p)
                _row = trade_row(df.index, _entry_i, i, position["direction"], p)
                if _row is not None:
                    trade_profits.times.append(_row)
                position = None

        # ── Проверка входа ──
        if position is None:
            entry_dir = check_entry(prev_acf, curr_acf, threshold)
            if entry_dir == 'long':
                entry = curr_close + spread
                _entry_i = i
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close - spread
                _entry_i = i
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
