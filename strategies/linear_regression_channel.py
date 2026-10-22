"""Стратегия Linear Regression Channel — вход при выходе за пределы ±2σ, выход при возврате."""
import numpy as np
import pandas as pd

try:
    from numpy.lib.stride_tricks import sliding_window_view
except ImportError:  # numpy < 1.20
    def sliding_window_view(a, w):
        shape = (a.size - w + 1, w)
        strides = (a.strides[0], a.strides[0])
        return np.lib.stride_tricks.as_strided(a, shape=shape, strides=strides)


def calc_lr_channel(df, lr_period, sigma_mult=2.0):
    """
    Добавляет колонки 'lr_line', 'lr_upper', 'lr_lower' с линией регрессии и каналами.

    Args:
        df: DataFrame с OHLCV
        lr_period: период для линейной регрессии
        sigma_mult: множитель стандартного отклонения для каналов

    Returns:
        DataFrame с колонками 'lr_line', 'lr_upper', 'lr_lower', 'lr_signal'
    """
    df = df.copy()
    n = len(df)
    p = int(lr_period)

    # ── Линейная регрессия по окну (векторно, без цикла по барам) ──
    # Окно y = close[i-p+1 : i+1] (p значений), x = arange(p). Регрессия y = a + b·x:
    # b = Σ(x-xm)(y-ym)/Σ(x-xm)², a = ym - b·xm, линия в последней точке: a + b·(p-1).
    # σ — по остаткам y - (a + b·x) как numpy .std() (ddof=0, population: y берётся .values).
    # как в старом коде; для i < p-1 линия/каналы равны close[i].
    lr_line = np.empty(n, dtype=float)
    lr_upper = np.empty(n, dtype=float)
    lr_lower = np.empty(n, dtype=float)

    close_arr = df['close'].to_numpy(dtype=float)
    head = min(max(p - 1, 0), n)          # i < p-1 → проход цены как есть
    if head > 0:
        lr_line[:head] = close_arr[:head]
        lr_upper[:head] = close_arr[:head]
        lr_lower[:head] = close_arr[:head]

    if p >= 1 and n >= p:
        x = np.arange(p, dtype=float)
        x_mean = x.mean()
        xc = x - x_mean
        den = (xc * xc).sum()
        windows = sliding_window_view(close_arr, p)      # строки s: close[s : s+p], бар i = s+p-1
        chunk = max(1, 2_000_000 // p)
        total = n - p + 1
        with np.errstate(divide='ignore', invalid='ignore'):
            for start in range(0, total, chunk):
                stop = min(start + chunk, total)
                block = windows[start:stop]
                y_mean = block.mean(axis=1)
                num = ((block - y_mean[:, None]) * xc).sum(axis=1)
                if den == 0:
                    a = y_mean
                    b = np.zeros_like(y_mean)
                else:
                    b = num / den
                    a = y_mean - b * x_mean
                line = a + b * (p - 1)
                residuals = block - (a[:, None] + b[:, None] * x)
                std = residuals.std(axis=1)                # ddof=0 — как numpy .std() на .values
                dst = slice(start + p - 1, stop + p - 1)
                lr_line[dst] = line
                lr_upper[dst] = line + sigma_mult * std
                lr_lower[dst] = line - sigma_mult * std

    df['lr_line'] = lr_line
    df['lr_upper'] = lr_upper
    df['lr_lower'] = lr_lower

    # Сигнал: цена выше верхней границы → short, ниже нижней → long
    df['lr_signal'] = 0
    df.loc[df['close'] > df['lr_upper'], 'lr_signal'] = -1
    df.loc[df['close'] < df['lr_lower'], 'lr_signal'] = 1

    return df


def check_entry(prev_signal, curr_signal):
    """
    Вход при уходе цены за пределы канала.

    Returns:
        'long', 'short' или None
    """
    # Long: был нейтральный сигнал (0), теперь цена ниже нижней границы
    if prev_signal == 0 and curr_signal == 1:
        return 'long'
    # Short: был нейтральный сигнал (0), теперь цена выше верхней границы
    if prev_signal == 0 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при возврате к линии регрессии.

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


def backtest(df, lr_period, sigma_mult, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Linear Regression Channel.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_lr_channel(df, lr_period, sigma_mult)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    from strategies._bt_core import TradeList, trade_row  # v2: журнал сделок
    trade_profits = TradeList()

    _c_lr_signal = df['lr_signal'].to_numpy()   # numpy-петля: позиционный доступ
    _c_close = df['close'].to_numpy()   # numpy-петля: позиционный доступ
    _c_high = df['high'].to_numpy()   # numpy-петля: позиционный доступ
    _c_low = df['low'].to_numpy()   # numpy-петля: позиционный доступ
    for i in range(1, len(df)):
        prev_signal = _c_lr_signal[i - 1]
        curr_signal = _c_lr_signal[i]
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
