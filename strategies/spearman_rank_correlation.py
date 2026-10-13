"""Spearman Rank correlation, каталог #17.

Сигнал: ранговая корреляция цены и объёма > порога → вход по направлению движения.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
Движок бэктеста общий — strategies/_bt_core.py.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

CORR_THRESHOLD = 0.5

# Размер чанка окон при векторизации: ограничивает пиковую память O(chunk * period^2).
_RANK_CHUNK = 1024


def _row_avg_ranks(x):
    """Средние ранги (1-based) по строкам матрицы x формы (m, w).

    Эквивалент pandas.rank(method='average') для каждой строки:
    rank = (#меньших) + (#равных + 1) / 2.
    """
    less = (x[:, :, None] > x[:, None, :]).sum(axis=2)
    eq = (x[:, :, None] == x[:, None, :]).sum(axis=2)
    return less + (eq + 1) * 0.5


def _rolling_spearman(a, b, w):
    """Скользящая ранговая корреляция Спирмена для окон длины w.

    Векторизовано по чанкам (без по-барового Python-цикла): для каждого окна
    считаются средние ранги обеих серий, затем берётся корреляция Пирсона по
    рангам (== Спирмен). Память ограничена размером чанка.
    """
    n = len(a)
    m = n - w + 1
    out = np.zeros(m)
    sw = np.lib.stride_tricks.sliding_window_view
    for s in range(0, m, _RANK_CHUNK):
        e = min(s + _RANK_CHUNK, m)
        wa = sw(a[s:e + w - 1], w)
        wb = sw(b[s:e + w - 1], w)
        ra = _row_avg_ranks(wa)
        rb = _row_avg_ranks(wb)
        ra -= ra.mean(axis=1, keepdims=True)
        rb -= rb.mean(axis=1, keepdims=True)
        num = (ra * rb).sum(axis=1)
        den = np.sqrt((ra * ra).sum(axis=1) * (rb * rb).sum(axis=1))
        out[s:e] = np.where(den > 0.0, num / den, 0.0)
    return out


def calc_spearman(df, period):
    """period — окно корреляции. Колонка 'k' — состояние позиции."""
    c = df['close'].to_numpy(dtype=float)
    v = df['volume'].to_numpy(dtype=float)
    n = len(df)
    w = int(period)
    corr = np.zeros(n)
    if w >= 2 and n >= w:
        corr[w - 1:] = _rolling_spearman(c, v, w)
    direction = np.sign(np.diff(c, prepend=c[0]))
    state = np.where(corr > CORR_THRESHOLD, np.where(direction >= 0, 1, -1), 0)
    df = df.copy()
    df['k'] = state
    return df


def check_entry(prev_s, curr_s):
    return state_entry(prev_s, curr_s)


def check_exit(prev_s, curr_s, direction):
    return state_exit(prev_s, curr_s, direction)


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_spearman, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
