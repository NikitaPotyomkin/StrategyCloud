"""Mean Reversion: Distance Percentile (H1).

Idea: 0884 mr_distance_percentile
Вход: расстояние до MA(20) > p95(500)
Выход: p50
Отличие: Процентиль расстояния вместо абсолютного z-score
"""
import numpy as np
import pandas as pd


def calc_mr_distance_percentile(df, param_key):
    """Процентиль расстояния цены от MA."""
    parts = str(param_key).split(',') if isinstance(param_key, str) else [str(param_key)]
    ma_period = int(parts[0]) if len(parts) > 0 else 20
    win_period = int(parts[1]) if len(parts) > 1 else 500
    ma = df['close'].rolling(ma_period).mean()
    distance = (df['close'] - ma).abs()

    # (right) rolling percentile через apply
    p95 = distance.rolling(win_period).apply(
        lambda x: np.percentile(x, 95) if len(x) > 10 else np.nan, raw=True
    )
    p50 = distance.rolling(win_period).apply(
        lambda x: np.percentile(x, 50) if len(x) > 10 else np.nan, raw=True
    )

    sign = np.sign(df['close'] - ma)

    k = np.zeros(len(df))
    k[(distance > p95) & (sign > 0)] = 1   # цена выше MA на экстремуме
    k[(distance > p95) & (sign < 0)] = -1  # цена ниже MA на экстремуме

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
def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    """Симуляция через общий движок strategies/_bt_core.run_backtest.

    Вход по open следующего бара ± спред, спред вычитается и на выходе, обрыва
    по времени нет, деньги через trade_profit (÷ tick_size). Прежняя петля
    входила по close сигнального бара, не вычитала спред, выбрасывала сделки,
    не закрывшиеся за 49 баров, и считала P&L без деления на tick_size —
    из-за этого её числа были несравнимы с остальным реестром.
    """
    return run_backtest(df, calc_mr_distance_percentile, check_entry, check_exit,
                        param_key, sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
