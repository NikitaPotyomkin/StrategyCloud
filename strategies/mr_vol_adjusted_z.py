"""Mean Reversion: Vol-Adjusted Z (H1).

Idea: 0919 mr_vol_adjusted_z
Вход: z/σ > 2.5 (волатильностно нормированный)
Выход: 0
Отличие: Z-score нормирован на текущую волатильность
"""
import numpy as np
import pandas as pd


def calc_mr_vol_adjusted_z(df, param_key):
    """Волатильностно нормированный z-score."""
    period = int(param_key) if not isinstance(param_key, str) or ',' not in str(param_key) else 100
    ma = df['close'].rolling(period).mean()
    vol = df['close'].pct_change().rolling(period).std()
    ret = df['close'].pct_change()

    # (right) z-score нормирован на волатильность
    z = ret / (vol + 1e-12)

    k = np.zeros(len(df))
    k[z > 2.5] = 1
    k[z < -2.5] = -1

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
    return run_backtest(df, calc_mr_vol_adjusted_z, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
