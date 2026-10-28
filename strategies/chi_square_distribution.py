"""Стратегия Chi-square distribution — вход при p-value < 0.05 И направлении mean_ret.

Хи-квадрат тест проверяет СТАТИСТИЧЕСКУЮ ЗНАЧИМОСТЬ отклонения долей
положительных/отрицательных возвратов от 50/50. Сам по себе p-value НЕ даёт
направления — поэтому направление задаёт mean_ret (средний возврат за окно).

Вход: p-value < 0.05 (статистическая значимость) + mean_ret > 0 → LONG
      p-value < 0.05 (статистическая значимость) + mean_ret < 0 → SHORT
Выход: p-value > 0.2 (статистическая значимость потеряна)

ВЕКТОРИЗАЦИЯ (22.10.2026)
    Раньше на КАЖДОМ баре создавался срез Series (returns.iloc[i-window:i] →
    dropna), два булевых индекса (positive/negative) и вызывался скалярный
    scipy.stats.chi2.cdf. При 719 барах, 9 парах SL/TP и 324 комбинациях это
    давало 22 мин из 82 на всю корзину — 26% прогона, больше любого другого
    семейства. Теперь то же самое считается массивами:
        * доли pos/neg — из накопленных сумм (cumsum), окно = разность;
        * p-value для 1 степени свободы: 1 - chi2.cdf(x, 1) ≡ erfc(sqrt(x/2)),
          считается один раз на весь вектор;
        * scipy.stats из горячего пути убран (остался scipy.special.erfc).
    Формула, пороги и колонки не изменились: паритет — tools/calc_vector_parity.py.
"""
import numpy as np
import pandas as pd

try:
    from scipy.special import erfc as _erfc          # векторный erfc — быстрый путь
except ImportError:                                  # scipy нет — math.erfc по одному
    from math import erfc as _math_erfc

    def _erfc(x):
        return np.array([_math_erfc(float(v)) for v in np.asarray(x).ravel()],
                        dtype=float)


def calc_chi_square(df, window, p_entry=0.05, p_exit=0.2):
    """
    Добавляет колонки 'chi2_pvalue' и 'mean_ret' для определения направления.

    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        p_entry: порог p-value для входа
        p_exit: порог p-value для выхода

    Returns:
        DataFrame с колонками 'chi2_pvalue', 'mean_ret', 'trend_up', 'trend_down'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)
    df['mean_ret'] = returns.rolling(window, min_periods=1).mean()

    # ── Пропорции pos/neg по окну (window баров ДО текущего, без него) ──
    r = returns.to_numpy(dtype=float)
    n = len(r)
    cs_pos = np.concatenate(([0.0], np.cumsum((r > 0).astype(np.float64))))
    cs_neg = np.concatenate(([0.0], np.cumsum((r < 0).astype(np.float64))))
    idx = np.arange(n)
    start = np.maximum(idx - window, 0)
    n_pos = cs_pos[idx] - cs_pos[start]
    n_neg = cs_neg[idx] - cs_neg[start]
    n_total = np.minimum(idx, window).astype(np.float64)

    # ── p-value ──
    # Неполное окно (i < window) и вырожденные окна дают ровно 1.0, как раньше.
    p_values = np.ones(n, dtype=float)
    ok = (idx >= window) & (n_total >= 10) & (n_total >= 5) & (n_pos > 0) & (n_neg > 0)
    if ok.any():
        expected = n_total[ok] / 2.0
        chi2 = ((n_pos[ok] - expected) ** 2 / expected +
                (n_neg[ok] - expected) ** 2 / expected)
        # Для 1 степени свободы: P(X > x) = erfc(sqrt(x / 2))
        p_values[ok] = _erfc(np.sqrt(chi2 / 2.0))

    df['chi2_pvalue'] = p_values

    # Направление по mean_ret (средний возврат за окно)
    df['trend_up'] = (df['chi2_pvalue'] < p_entry) & (df['mean_ret'] > 0)
    df['trend_down'] = (df['chi2_pvalue'] < p_entry) & (df['mean_ret'] < 0)
    return df


def check_entry(prev_up, prev_down, curr_up, curr_down):
    """
    Вход при появлении статистически значимого тренда с направлением.

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
    Выход при потере статистической значимости.

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


def backtest(df, window, p_entry, p_exit, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Chi-square distribution.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_chi_square(df, window, p_entry, p_exit)
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
