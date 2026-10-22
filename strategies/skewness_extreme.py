"""Стратегия Skewness extreme — вход при Skewness < -1 или > 1, выход при |Skewness| < 0.3."""
import numpy as np
import pandas as pd

try:
    from numpy.lib.stride_tricks import sliding_window_view
except ImportError:  # numpy < 1.20
    def sliding_window_view(a, w):
        shape = (a.size - w + 1, w)
        strides = (a.strides[0], a.strides[0])
        return np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)

# Пороги входа/выхода по умолчанию.
# Live (strategy_engine.check_active_signals) передаёт их из param_key аргументами
# check_entry/check_exit; бэктест — из грида SKEW_THRESHOLD_LIST.
SKEW_ENTRY = 1.0
SKEW_EXIT = 0.3


def calc_skewness(df, window, skew_entry=SKEW_ENTRY):
    """
    Добавляет колонку 'skewness' с коэффициентом асимметрии.

    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        skew_entry: порог входа (принимается для совместимости с контрактом
            движка; на сам расчёт асимметрии не влияет)

    Returns:
        DataFrame с колонкой 'skewness'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)

    # ── Skewness (векторно, без цикла по барам) ──
    # skew[i] = Σ(x-μ)^3 / (window·σ^3), окно returns[i-window:i] (БЕЗ текущего бара),
    # σ — выборочное (ddof=1) → μ/σ берём rolling(...).shift(1). Для i < window и при
    # σ == 0 или window < 3 → 0. Третий центральный момент — по скользящему окну чанками.
    r = returns.to_numpy(dtype=float)
    n = len(r)
    skew_values = np.zeros(n, dtype=float)

    if window >= 3 and n > window:
        mean_arr = returns.rolling(window).mean().shift(1).to_numpy()
        std_arr = returns.rolling(window).std().shift(1).to_numpy()   # ddof=1
        windows = sliding_window_view(r, window)             # (n-window+1, window)
        chunk = max(1, 2_000_000 // window)
        total = n - window
        for start in range(0, total, chunk):
            stop = min(start + chunk, total)
            block = windows[start:stop]
            dst = slice(start + window, stop + window)
            mu = mean_arr[dst, None]
            sd = std_arr[dst]
            m3 = ((block - mu) ** 3).sum(axis=1)
            good = sd != 0
            with np.errstate(divide='ignore', invalid='ignore'):
                skew = m3 / (window * sd ** 3)
            skew_values[dst] = np.where(good, skew, 0.0)

    df['skewness'] = skew_values
    return df


def check_entry(prev_skew, curr_skew, skew_entry=SKEW_ENTRY, skew_exit=SKEW_EXIT):
    """
    Вход при экстремальной асимметрии.

    Args:
        skew_entry: порог Skewness для входа (из грида/param_key)
        skew_exit: порог выхода — принимается для совместимости с контрактом
            движка (в проверке входа не используется)

    Returns:
        'long' (отрицательная skewness → хвост влево → разворот вверх),
        'short' (положительная) или None
    """
    # Long: был в нейтральной зоне, теперь skew < -skew_entry
    if prev_skew >= -skew_entry and curr_skew < -skew_entry:
        return 'long'
    # Short: был в нейтральной зоне, теперь skew > skew_entry
    if prev_skew <= skew_entry and curr_skew > skew_entry:
        return 'short'
    return None


def check_exit(prev_skew, curr_skew, skew_exit=SKEW_EXIT, direction=None):
    """
    Выход при возврате асимметрии к нулю.

    Args:
        skew_exit: порог Skewness для выхода (из грида/param_key)
        direction: 'long' или 'short'

    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_skew >= -skew_exit
    else:
        return curr_skew <= skew_exit


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, window, skew_entry, skew_exit, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Skewness extreme.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_skewness(df, window, skew_entry)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    from strategies._bt_core import TradeList, trade_row  # v2: журнал сделок
    trade_profits = TradeList()

    _c_skewness = df['skewness'].to_numpy()   # numpy-петля: позиционный доступ
    _c_close = df['close'].to_numpy()   # numpy-петля: позиционный доступ
    _c_high = df['high'].to_numpy()   # numpy-петля: позиционный доступ
    _c_low = df['low'].to_numpy()   # numpy-петля: позиционный доступ
    for i in range(1, len(df)):
        prev_skew = _c_skewness[i - 1]
        curr_skew = _c_skewness[i]
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
                elif check_exit(prev_skew, curr_skew, skew_exit, 'long'):
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
                elif check_exit(prev_skew, curr_skew, skew_exit, 'short'):
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
            entry_dir = check_entry(prev_skew, curr_skew, skew_entry, skew_exit)
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
