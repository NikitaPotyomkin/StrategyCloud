"""Стратегия Bayesian trend update — вход при P(тренд) > 0.65 И направлении mean_ret.

Байесовское обновление оценивает ВЕРОЯТНОСТЬ тренда, но НЕ его направление.
Направление задаётся mean_ret (средний возврат за окно).

Вход: P(тренд) > 0.65 + mean_ret > 0 → LONG
      P(тренд) > 0.65 + mean_ret < 0 → SHORT
Выход: P(тренд) < 0.5 (вероятность тренда потеряна)
"""
import numpy as np
import pandas as pd


def calc_bayesian_trend(df, window, prior=0.5, p_entry=0.65, p_exit=0.5):
    """
    Добавляет колонки 'p_trend' и 'mean_ret' для определения направления.

    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        prior: априорная вероятность тренда
        p_entry: порог вероятности для входа
        p_exit: порог вероятности для выхода

    Returns:
        DataFrame с колонками 'p_trend', 'mean_ret', 'trend_up', 'trend_down'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)
    df['mean_ret'] = returns.rolling(window, min_periods=1).mean()

    # ── Байесовское обновление (векторно по доле роста) ──
    # up_ratio[i] = доля положительных возвратов в окне returns[i-window:i] — считается
    # префиксными суммами (O(1) на бар) вместо среза returns.iloc[i-window:i].
    # Само обновление p_trend — последовательное (рекуррентное), но это уже чистая
    # арифметика без pandas, поэтому цикл дешёвый.
    r = returns.to_numpy(dtype=float)
    n = len(r)
    positive = (r > 0).astype(np.float64)
    cs = np.concatenate(([0.0], np.cumsum(positive)))    # cs[i] — positives в r[:i]

    p_trend_values = np.empty(n, dtype=float)
    p_trend = float(prior)
    w = float(window)

    for i in range(n):
        if i < window:
            p_trend_values[i] = p_trend
        else:
            up_ratio = (cs[i] - cs[i - window]) / w
            likelihood_up_given_trend = up_ratio
            likelihood_up_given_no_trend = 0.5
            p_up = (likelihood_up_given_trend * p_trend +
                    likelihood_up_given_no_trend * (1 - p_trend))
            if p_up > 0:
                p_trend = (likelihood_up_given_trend * p_trend) / p_up
            # Ограничиваем диапазон
            if p_trend < 0.01:
                p_trend = 0.01
            elif p_trend > 0.99:
                p_trend = 0.99
            p_trend_values[i] = p_trend

    df['p_trend'] = p_trend_values

    # Направление по mean_ret (средний возврат за окно)
    df['trend_up'] = (df['p_trend'] > p_entry) & (df['mean_ret'] > 0)
    df['trend_down'] = (df['p_trend'] > p_entry) & (df['mean_ret'] < 0)
    return df


def check_entry(prev_up, prev_down, curr_up, curr_down):
    """
    Вход при росте вероятности тренда с направлением.

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
    Выход при падении вероятности тренда.

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


def backtest(df, window, prior, p_entry, p_exit, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Bayesian trend update.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_bayesian_trend(df, window, prior, p_entry, p_exit)
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
