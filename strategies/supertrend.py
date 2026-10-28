"""Стратегия SuperTrend — вход при пробое линии SuperTrend."""
import numpy as np
import pandas as pd


def calc_supertrend(df, period=10, multiplier=3.0):
    """
    Добавляет колонку 'supertrend' с индикатором SuperTrend и сигналом.

    Args:
        df: DataFrame с OHLCV
        period: период для расчёта ATR
        multiplier: множитель ATR (по умолчанию 3.0)

    Returns:
        DataFrame с колонками 'supertrend', 'supertrend_signal'
    """
    df = df.copy()

    # Typical Price
    tp = (df['high'] + df['low'] + df['close']) / 3

    # ATR (Average True Range)
    tr1 = df['high'] - df['low']
    tr2 = abs(df['high'] - df['close'].shift())
    tr3 = abs(df['low'] - df['close'].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    # Basic Upper and Lower Bands
    basic_upper = tp + (multiplier * atr)
    basic_lower = tp - (multiplier * atr)

    # ── Final Upper / Lower Band и линия SuperTrend ──
    # Рекурсия по предыдущей полосе (сглаживание с «залипанием»), поэтому цикл остаётся,
    # но работает на numpy-массивах с локальными float вместо цепочки .iloc — порядок
    # вычислений и формулы идентичны старому коду (включая «залипание» NaN в начале серии).
    tp_arr = tp.to_numpy(dtype=float)
    bu_arr = basic_upper.to_numpy(dtype=float)
    bl_arr = basic_lower.to_numpy(dtype=float)
    n = len(df)
    final_upper = np.full(n, np.nan, dtype=float)
    final_lower = np.full(n, np.nan, dtype=float)
    supertrend = np.full(n, np.nan, dtype=float)

    if n > 0:
        final_upper[0] = bu_arr[0]
        final_lower[0] = bl_arr[0]
        supertrend[0] = bl_arr[0]

    for i in range(1, n):
        t = tp_arr[i]
        fu_prev = final_upper[i - 1]
        fl_prev = final_lower[i - 1]

        # Если цена выше предыдущей верхней границы — обновляем
        if t > fu_prev:
            final_upper[i] = bu_arr[i]
        elif t < fl_prev:
            final_upper[i] = fl_prev
        else:
            final_upper[i] = fu_prev

        # Если цена ниже предыдущей нижней границы — обновляем
        if t < fl_prev:
            final_lower[i] = bl_arr[i]
        elif t > fu_prev:
            final_lower[i] = fu_prev
        else:
            final_lower[i] = fl_prev

        # Определяем направление SuperTrend
        if t <= final_upper[i]:
            supertrend[i] = final_upper[i]
        else:
            supertrend[i] = final_lower[i]

    df['supertrend'] = supertrend
    df['final_upper'] = final_upper
    df['final_lower'] = final_lower

    # Сигнал: цена выше Supertrend → LONG, цена ниже Supertrend → SHORT
    df['supertrend_signal'] = 0
    df.loc[df['close'] > df['supertrend'], 'supertrend_signal'] = 1
    df.loc[df['close'] < df['supertrend'], 'supertrend_signal'] = -1

    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при смене направления SuperTrend.

    Returns:
        'long', 'short' или None
    """
    # Long: был neutral (0), теперь цена выше Supertrend
    if prev_signal == 0 and curr_signal == 1:
        return 'long'
    # Short: был neutral (0), теперь цена ниже Supertrend
    if prev_signal == 0 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при смене направления SuperTrend.

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


def backtest(df, period, multiplier, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с SuperTrend.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_supertrend(df, period, multiplier)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    from strategies._bt_core import TradeList, trade_row  # v2: журнал сделок
    trade_profits = TradeList()

    _c_supertrend_signal = df['supertrend_signal'].to_numpy()   # numpy-петля: позиционный доступ
    _c_close = df['close'].to_numpy()   # numpy-петля: позиционный доступ
    _c_high = df['high'].to_numpy()   # numpy-петля: позиционный доступ
    _c_low = df['low'].to_numpy()   # numpy-петля: позиционный доступ
    for i in range(1, len(df)):
        prev_signal = _c_supertrend_signal[i - 1]
        curr_signal = _c_supertrend_signal[i]
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
                entry = curr_close + spread  # pay ASK (close + spread)
                _entry_i = i
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close - spread  # receive BID (close - spread)
                _entry_i = i
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
