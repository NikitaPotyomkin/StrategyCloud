"""Стратегия Percentile reversion — вход в 5-м или 95-м перцентиле, выход к 50-му.

Percentile показывает позицию цены в распределении за окно.
- Percentile > 95 → цена выше 95% предыдущих значений (перекупленность)
- Percentile < 5 → цена ниже 95% предыдущих значений (перепроданность)

Вход LONG: цена была в 95-м перцентиле (высокая), теперь падает (< 95)
Вход SHORT: цена была в 5-м перцентиле (низкая), теперь растёт (> 5)

Это mean-reversion: ожидаем возврат к средней.
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


def calc_percentile(df, lookback, low_pct=5, high_pct=95, mid_pct=50):
    """
    Добавляет колонку 'percentile' с позицией цены в распределении.

    Args:
        df: DataFrame с OHLCV
        lookback: размер окна для расчёта перцентиля
        low_pct: нижний порог перцентиля
        high_pct: верхний порог перцентиля
        mid_pct: порог возврата (середина)

    Returns:
        DataFrame с колонкой 'percentile'
    """
    df = df.copy()

    # Перцентиль[i] = доля значений окна close[i-lookback:i], которые меньше close[i].
    # Векторно: скользящее окно (view) и сравнение с текущим значением по чанкам —
    # память ограничена (n × lookback не материализуется целиком).
    close = df['close'].to_numpy(dtype=float)
    n = len(close)
    percentiles = np.full(n, 50.0, dtype=float)   # i < lookback → 50 (как в старом цикле)

    if lookback > 0 and n > lookback:
        windows = sliding_window_view(close, lookback)   # (n-lookback+1, lookback)
        chunk = max(1, 2_000_000 // lookback)
        total = n - lookback
        for start in range(0, total, chunk):
            stop = min(start + chunk, total)
            block = windows[start:stop]
            current = close[start + lookback:stop + lookback, None]
            counts = (block < current).sum(axis=1)
            percentiles[start + lookback:stop + lookback] = counts / lookback * 100

    df['percentile'] = percentiles
    return df


def check_entry(prev_pct, curr_pct, low_pct, high_pct):
    """
    Вход при возврате перцентила ИЗ экстремума к середине (mean-reversion).

    Returns:
        'long' (цена была в перепроданности, теперь растёт), 'short' (цена была в перекупленности, теперь падает) или None
    """
    # Short: был в перекупленности (> high_pct), теперь падает (< high_pct)
    if prev_pct > high_pct and curr_pct <= high_pct:
        return 'short'
    # Long: был в перепроданности (< low_pct), теперь растёт (> low_pct)
    if prev_pct < low_pct and curr_pct >= low_pct:
        return 'long'
    return None


def check_exit(prev_pct, curr_pct, mid_pct, direction):
    """
    Выход при возврате к середине.

    Args:
        direction: 'long' или 'short'

    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_pct >= mid_pct
    else:
        return curr_pct <= mid_pct


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, lookback, low_pct, high_pct, mid_pct, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Percentile reversion.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_percentile(df, lookback, low_pct, high_pct, mid_pct)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    from strategies._bt_core import TradeList, trade_row  # v2: журнал сделок
    trade_profits = TradeList()

    _c_percentile = df['percentile'].to_numpy()   # numpy-петля: позиционный доступ
    _c_close = df['close'].to_numpy()   # numpy-петля: позиционный доступ
    _c_high = df['high'].to_numpy()   # numpy-петля: позиционный доступ
    _c_low = df['low'].to_numpy()   # numpy-петля: позиционный доступ
    for i in range(1, len(df)):
        prev_pct = _c_percentile[i - 1]
        curr_pct = _c_percentile[i]
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
                elif check_exit(prev_pct, curr_pct, mid_pct, 'long'):
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
                elif check_exit(prev_pct, curr_pct, mid_pct, 'short'):
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
            entry_dir = check_entry(prev_pct, curr_pct, low_pct, high_pct)
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
