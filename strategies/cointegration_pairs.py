"""Стратегия Cointegration pairs — вход при отклонении спреда > 2σ, выход при возврате."""
import numpy as np
import pandas as pd

try:
    from numpy.lib.stride_tricks import sliding_window_view
except ImportError:  # numpy < 1.20
    def sliding_window_view(a, w):
        shape = (a.size - w + 1, w)
        strides = (a.strides[0], a.strides[0])
        return np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)


def calc_cointegration(df, window, z_entry=2.0, z_exit=0.0):
    """
    Добавляет колонку 'spread_z' с Z-скор спреда.

    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта спреда
        z_entry: порог Z для входа
        z_exit: порог Z для выхода

    Returns:
        DataFrame с колонкой 'spread_z'
    """
    df = df.copy()

    # ── Z-скор спреда (векторно, без цикла по барам) ──
    # z[i] = (close[i] - μ) / σ по окну close[i-window:i] (БЕЗ текущего бара),
    # σ — выборочное (ddof=1). μ и σ считаем по тому же срезу окна (np.mean / np.std ddof=1) —
    # ровно то, что делает pandas .mean()/.std() на срезе Series (двухпроходная формула),
    # чтобы не ловить расхождение 1e-9 из-за алгоритма rolling-дисперсии.
    # Обработка чанками — память ограничена. Для i < window → 0; при σ == 0 → 0.
    close_arr = df['close'].to_numpy(dtype=float)
    n = len(df)
    z_values = np.zeros(n, dtype=float)

    if window > 0 and n > window:
        windows = sliding_window_view(close_arr, window)     # строки s: close[s : s+window]
        chunk = max(1, 2_000_000 // window)
        total = n - window
        for start in range(0, total, chunk):
            stop = min(start + chunk, total)
            block = windows[start:stop]
            dst = slice(start + window, stop + window)
            mu = block.mean(axis=1)
            with np.errstate(divide='ignore', invalid='ignore'):
                sd = block.std(axis=1, ddof=1)               # выборочное σ (ddof=1)
                z = (close_arr[dst] - mu) / sd
            z_values[dst] = np.where(sd != 0, z, 0.0)

    df['spread_z'] = z_values
    return df


def check_entry(prev_z, curr_z, z_entry):
    """
    Вход при уходе спреда ЗА пределы нейтральной зоны.

    Returns:
        'long', 'short' или None
    """
    # Long: был ниже -z_entry (перепроданность), теперь вернулся внутрь
    if prev_z < -z_entry and curr_z >= -z_entry:
        return 'long'
    # Short: был выше z_entry (перекупленность), теперь вернулся внутрь
    if prev_z > z_entry and curr_z <= z_entry:
        return 'short'
    return None


def check_exit(prev_z, curr_z, z_exit, direction):
    """
    Выход при возврате спреда к нулю.

    Args:
        direction: 'long' или 'short'

    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_z >= z_exit
    else:
        return curr_z <= z_exit


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, window, z_entry, z_exit, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Cointegration pairs.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_cointegration(df, window, z_entry, z_exit)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    from strategies._bt_core import TradeList, trade_row  # v2: журнал сделок
    trade_profits = TradeList()

    _c_spread_z = df['spread_z'].to_numpy()   # numpy-петля: позиционный доступ
    _c_close = df['close'].to_numpy()   # numpy-петля: позиционный доступ
    _c_high = df['high'].to_numpy()   # numpy-петля: позиционный доступ
    _c_low = df['low'].to_numpy()   # numpy-петля: позиционный доступ
    for i in range(1, len(df)):
        prev_z = _c_spread_z[i - 1]
        curr_z = _c_spread_z[i]
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
                elif check_exit(prev_z, curr_z, z_exit, 'long'):
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
                elif check_exit(prev_z, curr_z, z_exit, 'short'):
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
            entry_dir = check_entry(prev_z, curr_z, z_entry)
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
