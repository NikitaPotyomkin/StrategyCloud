"""Стратегия Morning/Evening Star — вход при разворотной паттерне из 3 свечей."""
import numpy as np
import pandas as pd


def calc_morning_evening_star(df, min_body_ratio=0.3):
    """
    Добавляет колонку 'star_signal' с сигналом разворотного паттерна Morning/Evening Star.

    Args:
        df: DataFrame с OHLCV
        min_body_ratio: минимальное отношение тела первой свечи к диапазону (по умолчанию 0.3)

    Returns:
        DataFrame с колонкой 'star_signal'
    """
    df = df.copy()

    # Расчёт параметров свечи
    df['body'] = abs(df['close'] - df['open'])
    df['range'] = df['high'] - df['low']
    df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
    df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']

    # Morning Star (бычий разворот):
    # 1. Первая свеча — длинная медвежья (close < open)
    # 2. Вторая свеча — маленькая (doji/spinning top), пробел от первой
    # 3. Третья свеча — длинная бычья (close > open), закрывается в тело первой

    # Evening Star (медвежий разворот):
    # 1. Первая свеча — длинная бычья (close > open)
    # 2. Вторая свеча — маленькая (doji/spinning top), пробел от первой
    # 3. Третья свеча — длинная медвежья (close < open), закрывается в тело первой

    # ── Поиск паттерна (векторно, без цикла по барам) ──
    # Свеча 1 = i-2, свеча 2 = i-1, свеча 3 = i. Условия — как в старом коде
    # (свеча 1/2/3 по open/close/body/range). Morning проверяется первым, затем
    # Evening перезаписывает при совпадении обоих — тот же порядок, что в цикле.
    open_arr = df['open'].to_numpy(dtype=float)
    close_arr = df['close'].to_numpy(dtype=float)
    body_arr = df['body'].to_numpy(dtype=float)
    range_arr = df['range'].to_numpy(dtype=float)
    n = len(df)

    signal = np.zeros(n, dtype=int)
    if n > 2:
        c1 = close_arr[:-2]
        o1 = open_arr[:-2]
        o2 = open_arr[1:-1]
        c3 = close_arr[2:]
        o3 = open_arr[2:]
        body2 = body_arr[1:-1]
        range2 = range_arr[1:-1]
        body3 = body_arr[2:]
        range3 = range_arr[2:]

        is_doji2 = body2 < range2 * min_body_ratio          # Вторая свеча маленькая
        long_third = body3 > range3 * 0.6                   # Третья свеча длинная

        morning = ((c1 < o1) & is_doji2 & (c3 > o3) &       # первая медвежья, третья бычья
                   (o2 < c1) & (c3 > o1) & long_third)      # пробел вниз, закрытие в тело первой
        evening = ((c1 > o1) & is_doji2 & (c3 < o3) &       # первая бычья, третья медвежья
                   (o2 > c1) & (c3 < o1) & long_third)      # пробел вверх, закрытие в тело первой

        signal[2:][morning] = 1
        signal[2:][evening] = -1

    df['star_signal'] = signal

    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при появлении разворотного паттерна Morning/Evening Star.

    Returns:
        'long', 'short' или None
    """
    # Long: был нейтральный или short-сигнал, теперь Morning Star (бычий разворот)
    if prev_signal != 1 and curr_signal == 1:
        return 'long'
    # Short: был нейтральный или long-сигнал, теперь Evening Star (медвежий разворот)
    if prev_signal != -1 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при появлении противоположного сигнала.

    Args:
        direction: 'long' или 'short'

    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_signal <= 0
    else:
        return curr_signal >= 0


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, min_body_ratio, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Morning/Evening Star.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_morning_evening_star(df, min_body_ratio)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    from strategies._bt_core import TradeList, trade_row  # v2: журнал сделок
    trade_profits = TradeList()

    _c_star_signal = df['star_signal'].to_numpy()   # numpy-петля: позиционный доступ
    _c_close = df['close'].to_numpy()   # numpy-петля: позиционный доступ
    _c_high = df['high'].to_numpy()   # numpy-петля: позиционный доступ
    _c_low = df['low'].to_numpy()   # numpy-петля: позиционный доступ
    for i in range(1, len(df)):
        prev_signal = _c_star_signal[i - 1]
        curr_signal = _c_star_signal[i]
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
                elif check_exit(prev_signal, curr_signal, 'long'):
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
                elif check_exit(prev_signal, curr_signal, 'short'):
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
            entry_dir = check_entry(prev_signal, curr_signal)
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
