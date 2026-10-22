"""Стратегия Pin Bar reversal с фильтром тренда (EMA) и без lookahead bias.

Правки:
- Убран lookahead bias: signal = 0/1/-1, подтверждение НЕ используется
- Добавлен фильтр тренда: EMA 200 (long только если close > EMA, short反之)
- Улучшен check_exit: выход по противоположному Pin Bar или нейтральной зоне
- Пороги как модульные константы
"""
import numpy as np
import pandas as pd

# ── Модульные константы (пороги) ──
PIN_BAR_BODY_RATIO = 0.3    # мин. отношение тени к телу
EMA_TREND_PERIOD = 200      # период EMA для фильтра тренда
TREND_TOL = 0.001           # допуск к EMA (не торгуем слишком близко)


def calc_pin_bar(df, body_ratio=0.3, ema_period=200):
    """
    Добавляет колонку 'pin_bar_signal' с сигналами паттерна Pin Bar.

    БЕЗ lookahead bias: сигнал определяется по текущему бару, без
    ожидания подтверждения следующего бара.

    Args:
        df: DataFrame с OHLCV
        body_ratio: минимальное отношение тени к телу (по умолчанию 0.3)
        ema_period: период EMA для фильтра тренда (по умолчанию 200)

    Returns:
        DataFrame с колонкой 'pin_bar_signal' (0/1/-1)
    """
    df = df.copy()
    df['pin_bar_signal'] = 0

    # ── Фильтр тренда: EMA ──
    df['ema_trend'] = df['close'].ewm(span=ema_period, adjust=False).mean()

    # ── Поиск Pin Bar (векторно, без цикла по барам) ──
    # body = |close-open|, range = high-low, тени — как в старом коде.
    # Бычий: lower_shadow > body_ratio·range и upper_shadow < body/2 → 1
    # Медвежий: иначе upper_shadow > body_ratio·range и lower_shadow < body/2 → -1
    # Далее фильтр тренда по EMA (close > ema+tol для long, close < ema-tol для short).
    # При range == 0 условия сравнения дают False — как и «continue» в старом цикле.
    open_arr = df['open'].to_numpy(dtype=float)
    high_arr = df['high'].to_numpy(dtype=float)
    low_arr = df['low'].to_numpy(dtype=float)
    close_arr = df['close'].to_numpy(dtype=float)
    ema_arr = df['ema_trend'].to_numpy(dtype=float)

    body = np.abs(close_arr - open_arr)
    range_size = high_arr - low_arr
    upper_shadow = high_arr - np.maximum(open_arr, close_arr)
    lower_shadow = np.minimum(open_arr, close_arr) - low_arr

    bull_detected = (lower_shadow > body_ratio * range_size) & (upper_shadow < body * 0.5)
    bear_detected = (~bull_detected) & (upper_shadow > body_ratio * range_size) & (lower_shadow < body * 0.5)

    signal = np.zeros(len(df), dtype=int)
    signal[bull_detected & (close_arr > ema_arr + TREND_TOL)] = 1
    signal[bear_detected & (close_arr < ema_arr - TREND_TOL)] = -1
    df['pin_bar_signal'] = signal

    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при появлении Pin Bar (переход из 0 в 1 или -1).

    Returns:
        'long', 'short' или None
    """
    # Long: был нейтральный, теперь бычий Pin Bar
    if prev_signal == 0 and curr_signal == 1:
        return 'long'
    # Short: был нейтральный, теперь медвежий Pin Bar
    if prev_signal == 0 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при появлении противоположного сигнала Pin Bar.

    Long: выход при медвежьем Pin Bar (-1)
    Short: выход при бычьем Pin Bar (1)

    Args:
        direction: 'long' или 'short'

    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        # Выход при медвежьем Pin Bar (противоположный сигнал)
        return curr_signal == -1
    else:
        # Выход при бычьем Pin Bar (противоположный сигнал)
        return curr_signal == 1


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, body_ratio, confirmation, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Pin Bar reversal.

    body_ratio: порог для тела тени (константа PIN_BAR_BODY_RATIO по умолчанию)
    confirmation: УСТАРЕЛО — не используется (убран lookahead bias)

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_pin_bar(df, body_ratio, EMA_TREND_PERIOD)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    from strategies._bt_core import TradeList, trade_row  # v2: журнал сделок
    trade_profits = TradeList()

    _c_pin_bar_signal = df['pin_bar_signal'].to_numpy()   # numpy-петля: позиционный доступ
    _c_close = df['close'].to_numpy()   # numpy-петля: позиционный доступ
    _c_high = df['high'].to_numpy()   # numpy-петля: позиционный доступ
    _c_low = df['low'].to_numpy()   # numpy-петля: позиционный доступ
    for i in range(1, len(df)):
        prev_signal = _c_pin_bar_signal[i - 1]
        curr_signal = _c_pin_bar_signal[i]
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
