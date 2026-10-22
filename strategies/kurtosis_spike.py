"""Стратегия Kurtosis spike — вход при Kurtosis > 5 и последний бар > 1σ с направлением.

Kurtosis (эксцесс) показывает "тяжесть хвостов" распределения — высокий эксцесс
означает частые резкие движения. Но сам по себе Kurtosis НЕ даёт направления!

Направление задаётся знаком последнего возврата (current_return).

Вход: Kurtosis > 5 + |sigma| > 1 + current_return > 0 → LONG
      Kurtosis > 5 + |sigma| > 1 + current_return < 0 → SHORT
Выход: Kurtosis < 3 (экстремальность прошла)
"""
import numpy as np
import pandas as pd

try:
    from numpy.lib.stride_tricks import sliding_window_view
except ImportError:  # numpy < 1.20
    def sliding_window_view(a, w):
        shape = (a.size - w + 1, w)
        strides = (a.strides[0], a.strides[0])
        return np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)


def calc_kurtosis(df, window, kurt_entry=5.0, kurt_exit=3.0, sigma_mult=1.0):
    """
    Добавляет колонки 'kurtosis', 'sigma' и 'current_return' для определения направления.

    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        kurt_entry: порог Kurtosis для входа
        kurt_exit: порог Kurtosis для выхода
        sigma_mult: множитель стандартного отклонения

    Returns:
        DataFrame с колонками 'kurtosis', 'sigma', 'current_return', 'trend_up', 'trend_down'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)
    df['current_return'] = returns

    # ── Kurtosis и sigma (векторно, без цикла по барам) ──
    # kurt[i]  = Σ(x-μ)^4 / (window·σ^4) - 3, σ — выборочное (ddof=1), окно returns[i-window:i].
    # μ и σ берём штатными rolling-функциями pandas (как в старом коде); четвёртый
    # центральный момент считаем по скользящему окну (view) чанками — память ограничена.
    # Для i < window и при σ == 0 значения 0 (как в старом цикле).
    r = returns.to_numpy(dtype=float)
    n = len(r)
    kurt_values = np.zeros(n, dtype=float)
    sigma_values = np.zeros(n, dtype=float)

    if window >= 4 and n > window:
        # окно как в старом коде: returns[i-window:i] — БЕЗ текущего бара, поэтому rolling().shift(1)
        mean_arr = returns.rolling(window).mean().shift(1).to_numpy()
        std_arr = returns.rolling(window).std().shift(1).to_numpy()   # ddof=1, окно без текущего бара
        windows = sliding_window_view(r, window)             # (n-window+1, window)
        chunk = max(1, 2_000_000 // window)
        total = n - window
        for start in range(0, total, chunk):
            stop = min(start + chunk, total)
            block = windows[start:stop]
            dst = slice(start + window, stop + window)
            mu = mean_arr[dst, None]
            sd = std_arr[dst]
            m4 = ((block - mu) ** 4).sum(axis=1)
            good = sd != 0
            with np.errstate(divide='ignore', invalid='ignore'):
                k = m4 / (window * sd ** 4) - 3.0
                sig = np.abs(r[dst] - mean_arr[dst]) / sd
            kurt_values[dst] = np.where(good, k, 0.0)
            sigma_values[dst] = np.where(good, sig, 0.0)

    df['kurtosis'] = kurt_values
    df['sigma'] = sigma_values

    # Направление по знаку current_return (текущий возврат)
    df['trend_up'] = (df['kurtosis'] > kurt_entry) & (df['sigma'] > sigma_mult) & (df['current_return'] > 0)
    df['trend_down'] = (df['kurtosis'] > kurt_entry) & (df['sigma'] > sigma_mult) & (df['current_return'] < 0)
    return df


def check_entry(prev_up, prev_down, curr_up, curr_down):
    """
    Вход при высоком эксцессе и большом последнем баре с направлением.

    Returns:
        'long' — экстремальное восходящее движение, 'short' — нисходящее, None — иначе
    """
    if curr_up and not prev_up:
        return 'long'
    if curr_down and not prev_down:
        return 'short'
    return None


def check_exit(prev_up, prev_down, curr_up, curr_down, direction):
    """
    Выход при падении эксцесса.

    Args:
        direction: 'long' или 'short'

    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return not curr_up
    else:
        return not curr_down


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, window, kurt_entry, kurt_exit, sigma_mult, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Kurtosis spike.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_kurtosis(df, window, kurt_entry, kurt_exit, sigma_mult)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    from strategies._bt_core import TradeList, trade_row  # v2: журнал сделок
    trade_profits = TradeList()

    _c_trend_up = df['trend_up'].to_numpy()   # numpy-петля: позиционный доступ
    _c_trend_down = df['trend_down'].to_numpy()   # numpy-петля: позиционный доступ
    _c_close = df['close'].to_numpy()   # numpy-петля: позиционный доступ
    _c_high = df['high'].to_numpy()   # numpy-петля: позиционный доступ
    _c_low = df['low'].to_numpy()   # numpy-петля: позиционный доступ
    for i in range(1, len(df)):
        prev_up = _c_trend_up[i - 1]
        prev_down = _c_trend_down[i - 1]
        curr_up = _c_trend_up[i]
        curr_down = _c_trend_down[i]
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
                elif check_exit(prev_up, prev_down, curr_up, curr_down, 'long'):
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
                elif check_exit(prev_up, prev_down, curr_up, curr_down, 'short'):
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
            entry_dir = check_entry(prev_up, prev_down, curr_up, curr_down)
            if entry_dir == 'long':
                entry = curr_close - spread
                _entry_i = i
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close + spread
                _entry_i = i
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
