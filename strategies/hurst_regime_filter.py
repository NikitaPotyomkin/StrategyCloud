"""Стратегия Hurst regime filter — вход при H > 0.6 (тренд), выход при H < 0.5."""
import numpy as np
import pandas as pd

try:
    from numpy.lib.stride_tricks import sliding_window_view
except ImportError:  # numpy < 1.20
    def sliding_window_view(a, w):
        shape = (a.size - w + 1, w)
        strides = (a.strides[0], a.strides[0])
        return np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)


def calc_hurst(df, window, h_threshold=0.6, h_exit=0.5):
    """
    Добавляет колонку 'hurst' с показателем Хёрста скользящим окном.

    Args:
        df: DataFrame с OHLCV
        window: размер скользящего окна
        h_threshold: порог H для входа в тренд
        h_exit: порог H для выхода из тренда

    Returns:
        DataFrame с колонкой 'hurst'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)

    # ── Hurst R/S (векторно, без цикла по барам) ──
    # H = log(R/S) / log(n), R — размах накопленных отклонений x-μ внутри окна
    # returns[i-window:i], S — выборочное σ (ddof=1). Для i < window → 0.5,
    # при σ == 0 или R == 0 → 0.5. Накопленные суммы и размах считаем по
    # скользящему окну (view) чанками — память ограничена.
    r = returns.to_numpy(dtype=float)
    n = len(r)
    w = int(window)
    hurst_values = np.full(n, 0.5, dtype=float)

    if w > 1 and n > w:
        # окно как в старом коде: returns[i-window:i] — БЕЗ текущего бара, поэтому rolling().shift(1)
        mean_arr = returns.rolling(w).mean().shift(1).to_numpy()
        std_arr = returns.rolling(w).std().shift(1).to_numpy()   # ddof=1, окно без текущего бара
        windows = sliding_window_view(r, w)             # строки s: r[s : s+w]
        chunk = max(1, 2_000_000 // w)
        total = n - w                                   # s = 0 .. n-1-w  → i = s+w
        for start in range(0, total, chunk):
            stop = min(start + chunk, total)
            block = windows[start:stop]
            dst = slice(start + w, stop + w)
            mu = mean_arr[dst, None]
            sd = std_arr[dst]
            cumulative = np.cumsum(block - mu, axis=1)
            range_rs = cumulative.max(axis=1) - cumulative.min(axis=1)
            good = (sd != 0) & (range_rs > 0)
            with np.errstate(divide='ignore', invalid='ignore'):
                h = np.log(range_rs / sd) / np.log(w)
            hurst_values[dst] = np.where(good, h, 0.5)

    df['hurst'] = hurst_values
    df['mean_ret'] = returns.rolling(window, min_periods=1).mean()
    df['trend_up'] = (df['hurst'] > h_threshold) & (df['mean_ret'] > 0)
    df['trend_down'] = (df['hurst'] > h_threshold) & (df['mean_ret'] < 0)
    df['trend_exit'] = df['hurst'] < h_exit
    return df


def check_entry(prev_up, prev_down, curr_up, curr_down):
    """Вход при появлении сильного НАПРАВЛЕННОГО тренда (H>порога и знак mean_ret):
    H сам по себе не даёт знака, поэтому long/short различаются знаком среднего возврата за окно."""
    """
    Аудит: H (R/S) не несёт знака — направление входа задаёт знак среднего возврата за окно (mean_ret), H — фильтр силы тренда.

    Returns:
        'long' — появился сильный восходящий тренд, 'short' — нисходящий, None — иначе
    """
    if curr_up and not prev_up:
        return 'long'
    if curr_down and not prev_down:
        return 'short'
    return None


def check_exit(prev_up, prev_down, curr_up, curr_down, direction):
    """
    Выход при смене тренда.

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


def backtest(df, window, h_threshold, h_exit, sl_points, tp_points, point,
             tick_value, tick_size, vol_period=50, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Hurst regime filter.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_hurst(df, window, h_threshold, h_exit)
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
