"""Oscillator: Trend Intensity Index (H1).

Idea: 0331 osc_tii
Вход: TII > 70 (сильный тренд вверх)
Выход: TII < 30
Отличие: Индекс интенсивности тренда по знаковым барам
"""
import numpy as np
import pandas as pd


def calc_osc_tii(df, period=60):
    """Trend Intensity Index — отношение трендовых баров к общему диапазону."""
    # (right) используем rolling sum для подсчёта баров, закрывающихся выше open
    up_vol = df.where(df['close'] > df['open'], 0)['volume'] if 'volume' in df.columns else pd.Series(0, index=df.index)
    down_vol = df.where(df['close'] < df['open'], 0)['volume'] if 'volume' in df.columns else pd.Series(0, index=df.index)

    # (right) fillna для пустых значений
    up_vol = up_vol.fillna(0)
    down_vol = down_vol.fillna(0)

    total_vol = up_vol + down_vol + 1e-12
    tii = 100 * (up_vol.rolling(period).sum() - down_vol.rolling(period).sum()) / (total_vol.rolling(period).sum() + 1e-12)

    k = np.zeros(len(df))
    k[tii > 70] = 1
    k[tii < -70] = -1

    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # (right) Returns 'long' / 'short' / None for engine run_backtest
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
    return run_backtest(df, calc_osc_tii, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
