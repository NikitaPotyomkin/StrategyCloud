"""Стратегия BB squeeze-breakout — вход при сжатии полос и последующем пробое."""
import numpy as np
import pandas as pd


def calc_bb_squeeze(df, bb_period=20, bb_std=2.0, squeeze_pct=0.5):
    """
    Добавляет колонку 'bb_signal' с сигналом пробоя после сжатия Bollinger Bands.

    Args:
        df: DataFrame с OHLCV
        bb_period: период для расчёта Bollinger Bands
        bb_std: стандартное отклонение для Bollinger Bands
        squeeze_pct: относительный порог сжатия (процент от средней ширины)

    Returns:
        DataFrame с колонками 'bb_middle', 'bb_width', 'bb_squeezing', 'bb_signal'
    """
    df = df.copy()

    # Средняя линия (SMA)
    df['bb_middle'] = df['close'].rolling(bb_period).mean()

    # Стандартное отклонение
    bb_std_dev = df['close'].rolling(bb_period).std()

    # Верхняя и нижняя линии
    df['bb_upper'] = df['bb_middle'] + bb_std * bb_std_dev
    df['bb_lower'] = df['bb_middle'] - bb_std * bb_std_dev

    # Ширина полос (нормализованная — относительная)
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']

    # Определение сжатия: ширина полос меньше squeeze_pct от скользящей средней ширины
    # Используем rolling mean ширины с окном побольше для стабильной оценки
    rolling_window = max(bb_period * 2, 50)
    df['bb_width_ma'] = df['bb_width'].rolling(rolling_window, min_periods=20).mean()
    df['bb_squeezing'] = (df['bb_width'] < df['bb_width_ma'] * squeeze_pct).astype(int)

    # ── Сигнал пробоя (векторно, без цикла по барам) ──
    # squeeze_active[i] = bb_squeezing[i] для i >= 1 (состояние сбрасывается на каждом баре,
    # где сжатия нет), squeeze_active[0] = 0 — старый цикл начинался с i=1.
    # bb_signal[i] = ±1, если сжатие активно И цена закрытия вышла за полосу, иначе 0.
    n = len(df)
    squeezing = df['bb_squeezing'].to_numpy(dtype=np.int64)
    squeeze_active = np.zeros(n, dtype=int)
    if n > 1:
        squeeze_active[1:] = squeezing[1:]
    df['squeeze_active'] = squeeze_active

    close = df['close'].to_numpy(dtype=float)
    upper = df['bb_upper'].to_numpy(dtype=float)
    lower = df['bb_lower'].to_numpy(dtype=float)
    active = squeeze_active == 1
    up_break = active & (close > upper)      # NaN в полосах → False (как в pandas-сравнении)
    dn_break = active & (close < lower)
    signal = np.zeros(n, dtype=int)
    signal[up_break] = 1
    signal[dn_break] = -1
    df['bb_signal'] = signal

    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при пробое после сжатия Bollinger Bands.

    Returns:
        'long', 'short' или None
    """
    # Long: был нейтральный или short-сигнал, теперь пробой вверх
    if prev_signal != 1 and curr_signal == 1:
        return 'long'
    # Short: был нейтральный или long-сигнал, теперь пробой вниз
    if prev_signal != -1 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction, bb_middle=None, prev_close=None, curr_close=None):
    """
    Выход при возврате цены к средней линии BB или смене направления.

    Args:
        direction: 'long' или 'short'
        bb_middle: текущее значение bb_middle (опционально)
        prev_close: цена закрытия предыдущего бара
        curr_close: цена закрытия текущего бара

    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        # Выход если сигнал сменился на отрицательный
        if curr_signal < 0:
            return True
        # Выход если цена вернулась ниже средней линии BB
        if bb_middle is not None and curr_close is not None:
            if curr_close < bb_middle:
                return True
        # Выход если сигнал стал нейтральным и цена не показывает пробой
        if curr_signal == 0 and prev_signal == 0:
            return True
        return False
    else:
        # Выход если сигнал сменился на положительный
        if curr_signal > 0:
            return True
        # Выход если цена поднялась выше средней линии BB
        if bb_middle is not None and curr_close is not None:
            if curr_close > bb_middle:
                return True
        # Выход если сигнал стал нейтральным и цена не показывает пробой
        if curr_signal == 0 and prev_signal == 0:
            return True
        return False


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, bb_period, bb_std, squeeze_pct, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с BB squeeze-breakout.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_bb_squeeze(df, bb_period, bb_std, squeeze_pct)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    from strategies._bt_core import TradeList, trade_row  # v2: журнал сделок
    trade_profits = TradeList()

    _c_bb_signal = df['bb_signal'].to_numpy()   # numpy-петля: позиционный доступ
    _c_close = df['close'].to_numpy()   # numpy-петля: позиционный доступ
    _c_high = df['high'].to_numpy()   # numpy-петля: позиционный доступ
    _c_low = df['low'].to_numpy()   # numpy-петля: позиционный доступ
    _c_bb_middle = df['bb_middle'].to_numpy()   # numpy-петля: позиционный доступ
    for i in range(1, len(df)):
        prev_signal = _c_bb_signal[i - 1]
        curr_signal = _c_bb_signal[i]
        curr_close = _c_close[i]
        current_high = _c_high[i]
        current_low = _c_low[i]

        # ── Проверка выхода ──
        if position:
            exited = False
            p = 0.0
            d = position['direction']
            next_i = i + 1 if i + 1 < len(df) else i

            if d == 'long':
                if current_low <= position['sl']:
                    p = _profit(position['entry'], position['sl'],
                                tick_value, tick_size, sim_lot, 'long')
                    exited = True
                elif current_high >= position['tp']:
                    p = _profit(position['entry'], position['tp'],
                                tick_value, tick_size, sim_lot, 'long')
                    exited = True
                elif check_exit(prev_signal, curr_signal, 'long',
                               bb_middle=_c_bb_middle[next_i],
                               prev_close=_c_close[i-1] if i > 0 else curr_close,
                               curr_close=curr_close):
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
                elif check_exit(prev_signal, curr_signal, 'short',
                               bb_middle=_c_bb_middle[next_i],
                               prev_close=_c_close[i-1] if i > 0 else curr_close,
                               curr_close=curr_close):
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
