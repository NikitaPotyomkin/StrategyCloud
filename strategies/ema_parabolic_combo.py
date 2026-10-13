"""EMA + Parabolic combo, каталог #116.

Сигнал: кросс EMA(period)/EMA(2.5·period) подтверждён направлением Parabolic SAR.
Standalone-модуль: не подключён к main/dispatcher.
Состояние 'k': +1 long, -1 short, 0 — нет сигнала.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit

PSAR_STEP = 0.02
PSAR_MAX = 0.2


def _psar_dir(df):
    """Направление Parabolic SAR: +1 вверх, -1 вниз."""
    high = df['high'].to_numpy(dtype=float)
    low = df['low'].to_numpy(dtype=float)
    n = len(df)
    direction = np.ones(n)
    psar = np.zeros(n)
    af = PSAR_STEP
    ep = high[0]
    psar[0] = low[0]
    for i in range(1, n):
        prev = psar[i - 1]
        if direction[i - 1] == 1:
            cur = prev + af * (ep - prev)
            cur = min(cur, low[i - 1], low[max(0, i - 2)])
            if low[i] < cur:
                direction[i] = -1
                cur = ep
                ep = low[i]
                af = PSAR_STEP
            else:
                direction[i] = 1
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + PSAR_STEP, PSAR_MAX)
        else:
            cur = prev + af * (ep - prev)
            cur = max(cur, high[i - 1], high[max(0, i - 2)])
            if high[i] > cur:
                direction[i] = 1
                cur = ep
                ep = high[i]
                af = PSAR_STEP
            else:
                direction[i] = -1
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + PSAR_STEP, PSAR_MAX)
        psar[i] = cur
    return direction


def calc_ema_parabolic(df, period):
    """period — быстрая EMA; медленная = 2.5·period."""
    fast = df['close'].ewm(span=period, adjust=False).mean().to_numpy(dtype=float)
    slow = df['close'].ewm(span=int(period * 2.5), adjust=False).mean().to_numpy(dtype=float)
    psar = _psar_dir(df)
    up = (fast > slow) & (psar == 1)
    dn = (fast < slow) & (psar == -1)
    df = df.copy()
    df['k'] = np.where(up, 1, np.where(dn, -1, 0))
    return df


def check_entry(prev_s, curr_s):
    return state_entry(prev_s, curr_s)


def check_exit(prev_s, curr_s, direction):
    return state_exit(prev_s, curr_s, direction)


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits)."""
    return run_backtest(df, calc_ema_parabolic, check_entry, check_exit, param_key,
                        sl_points, tp_points, point, tick_value, tick_size,
                        sim_lot, spread_points)
