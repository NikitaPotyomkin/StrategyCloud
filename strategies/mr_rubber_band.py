"""Mean Reversion: Rubber Band (H1).

Idea: 0891 mr_rubber_band
Вход: перцентиль растяжения от MA > 95
Выход: перцентиль < 50
Отличие: Резиновая лента — возврат к среднему при экстремальном растяжении
"""
import numpy as np
import pandas as pd


def calc_mr_rubber_band(df, param_key):
    """Перцентиль расстояния от MA."""
    parts = str(param_key).split(',') if isinstance(param_key, str) else [str(param_key)]
    ma_period = int(parts[0]) if len(parts) > 0 else 20
    win_period = int(parts[1]) if len(parts) > 1 else 500
    ma = df['close'].rolling(ma_period).mean()
    stretch = (df['close'] - ma).abs()

    # (right) rolling percentile
    p95 = stretch.rolling(win_period).apply(
        lambda x: np.percentile(x, 95) if len(x) > 10 else np.nan, raw=True
    )
    p50 = stretch.rolling(win_period).apply(
        lambda x: np.percentile(x, 50) if len(x) > 10 else np.nan, raw=True
    )

    sign = np.sign(df['close'] - ma)

    k = np.zeros(len(df))
    k[(stretch > p95) & (sign > 0)] = 1
    k[(stretch > p95) & (sign < 0)] = -1

    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Возвращает 'long' / 'short' / None для engine run_backtest
    if prev == 0 and curr == 1:
        return 'long'
    if prev == 0 and curr == -1:
        return 'short'
    return None


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


from strategies._bt_core import run_backtest
def _calc(df, param_key):
    """calc_* с параметрами, собранными из param_key."""
    parts = str(param_key).split(',') if isinstance(param_key, str) else [str(param_key)]
    ma_period = int(parts[0]) if len(parts) > 0 else 20
    win_period = int(parts[1]) if len(parts) > 1 else 500
    # calc_mr_rubber_band сам разбирает param_key («ma,win»). Обёртка собирала те же
    # параметры вручную и звала его с тремя аргументами — TypeError на каждой
    # комбинации, и семейство молча выпадало через _safe_backtest.
    return calc_mr_rubber_band(df, param_key)


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    """Симуляция через общий движок strategies/_bt_core.run_backtest.

    Вход по open следующего бара ± спред, спред вычитается и на выходе, обрыва
    по времени нет, деньги через trade_profit (÷ tick_size). Прежняя петля
    входила по close сигнального бара, не вычитала спред, выбрасывала сделки,
    не закрывшиеся за 49 баров, и считала P&L без деления на tick_size —
    из-за этого её числа были несравнимы с остальным реестром.
    """
    return run_backtest(df, _calc, check_entry, check_exit,
                        param_key, sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
