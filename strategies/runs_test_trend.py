"""Стратегия Runs Test trend — вход при Z-stat > 1.96 (тренд) И mean_ret > 0.

Runs test проверяет СТАТИСТИЧЕСКУЮ ЗНАЧИМОСТЬ тренда (мало серий = тренд).
Но сам по себе Z-stat НЕ даёт направления — нужно mean_ret.

Вход LONG: Z > 1.96 (тренд) + mean_ret > 0 (восходящий)
Вход SHORT: Z < -1.96 (тренд) + mean_ret < 0 (нисходящий)
Выход: Z < 0 (тренд потерялся)

ВЕКТОРИЗАЦИЯ (22.10.2026)
    Раньше на КАЖДОМ баре: срез close.iloc[i-window:i] → shift → сравнение →
    astype(int) → dropna, затем ВНУТРЕННИЙ питоновский цикл по окну для подсчёта
    серий. Это O(window) на бар, то есть O(n·window) на колонку — 294 мс на
    вызов из 9 пар, второе место в корзине.
    Теперь число серий считается по префиксным суммам признаков «вырос/упал»
    и «знак сменился», за O(1) на бар. Формула, пороги и колонки не изменились:
    паритет — tools/calc_vector_parity.py.
"""
import numpy as np
import pandas as pd


def calc_runs_test(df, window, z_threshold=1.96):
    """
    Добавляет колонки 'z_stat' и 'mean_ret' для определения направления.

    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        z_threshold: порог Z для входа

    Returns:
        DataFrame с колонками 'z_stat', 'mean_ret', 'trend_up', 'trend_down'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)
    df['mean_ret'] = returns.rolling(window, min_periods=1).mean()

    c = df['close'].to_numpy(dtype=float)
    n_bars = len(c)

    # up[k] = 1, если бар k выше предыдущего. up[0] = 0 — это тот же «нулевой»
    # элемент, что давало сравнение с NaN от x.shift(1) в первом баре окна
    # (NaN-сравнение → False → 0), поэтому dropna() в старом коде ничего не резал.
    up = np.zeros(n_bars)
    up[1:] = (c[1:] > c[:-1]).astype(np.float64)
    chg = np.zeros(n_bars)                 # chg[k] = 1, если знак сменился между k-1 и k
    chg[1:] = (up[1:] != up[:-1]).astype(np.float64)
    cs_up = np.concatenate(([0.0], np.cumsum(up)))      # префиксные суммы
    cs_chg = np.concatenate(([0.0], np.cumsum(chg)))

    z_values = np.zeros(n_bars, dtype=float)
    idx = np.arange(n_bars)
    ok = idx >= window
    if ok.any():
        i = idx[ok]
        s1 = i - window + 1                # первый «настоящий» up внутри окна
        s2 = i - window + 2                # с него считаем смены знака
        n = float(window)
        n1 = cs_up[i] - cs_up[s1]          # число ростов в окне
        n2 = n - n1
        # серии = 1 (стартовая) + переход от ведущего нуля + смены знака внутри окна
        runs = 1.0 + up[s1] + (cs_chg[i] - cs_chg[s2])
        with np.errstate(divide='ignore', invalid='ignore'):
            expected = 2.0 * n1 * n2 / (n1 + n2) + 1.0
            variance = (2.0 * n1 * n2 * (2.0 * n1 * n2 - n1 - n2) /
                        ((n1 + n2) ** 2 * (n1 + n2 - 1.0)))
            z = (runs - expected) / np.sqrt(variance)
        good = (n >= 10) & (n1 > 0) & (n2 > 0) & (variance > 0) & np.isfinite(z)
        z_values[ok] = np.where(good, z, 0.0)

    df['z_stat'] = z_values

    # Направление по mean_ret (средний возврат за окно)
    df['trend_up'] = (df['z_stat'] > z_threshold) & (df['mean_ret'] > 0)
    df['trend_down'] = (df['z_stat'] < -z_threshold) & (df['mean_ret'] < 0)
    return df


def check_entry(prev_up, prev_down, curr_up, curr_down):
    """
    Вход при статистически значимом тренде с направлением.

    Returns:
        'long' — восходящий тренд, 'short' — нисходящий, None — иначе
    """
    if curr_up and not prev_up:
        return 'long'
    if curr_down and not prev_down:
        return 'short'
    return None


def check_exit(prev_up, prev_down, curr_up, curr_down, direction):
    """
    Выход при потере тренда.

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


def backtest(df, window, z_threshold, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Runs Test trend.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_runs_test(df, window, z_threshold)
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
