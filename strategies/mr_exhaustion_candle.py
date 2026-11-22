"""Mean Reversion: Exhaustion Candle (H1).

Idea: 0894 mr_exhaustion_candle
Вход: бар с телом < 5% диапазона на экстремуме 20 баров
Выход: 1.5 ATR
Отличие: Свеча истощения после длительного движения
"""
import numpy as np
import pandas as pd


def calc_mr_exhaustion_candle(df, param_key):
    """Маленькое тело на экстремуме."""
    period = int(param_key) if not isinstance(param_key, str) or ',' not in str(param_key) else 20
    body = (df['close'] - df['open']).abs()
    range_ = df['high'] - df['low']
    body_ratio = body / (range_ + 1e-12)

    high_ext = df['high'].rolling(period).max()
    low_ext = df['low'].rolling(period).min()

    k = np.zeros(len(df))
    # (right) тело < 5% диапазона и цена у экстремума
    k[(body_ratio < 0.05) & (df['high'] >= high_ext)] = 1    # дожи на максимуме
    k[(body_ratio < 0.05) & (df['low'] <= low_ext)] = -1     # дожи на минимуме

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
    return run_backtest(df, calc_mr_exhaustion_candle, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
