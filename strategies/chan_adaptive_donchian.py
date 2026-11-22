"""Channel: Adaptive Donchian (H1).

Idea: 0201 chan_adaptive_donchian
Вход: breakout Donchian with period = round(20/ER)
Выход: opposite boundary
Отличие: Adaptive period based on Efficiency Ratio
"""
import numpy as np
import pandas as pd


def calc_chan_adaptive_donchian(df, period=20):
    change = abs(df['close'] - df['close'].shift(period))
    vol = df['close'].diff().abs().rolling(period).sum()
    er = change / vol.replace(0, np.nan)
    
    # NaN на прогреве (первые `period` баров) и при нулевой волатильности:
    # astype(int) на NaN падал ValueError → нейтральное значение = period.
    adaptive_period = (20 / er).fillna(period).round().clip(5, 60).astype(int)
    
    k = np.zeros(len(df))
    for i in range(period, len(df)):
        p = int(adaptive_period.iloc[i])
        # Окно Donchian — СТРОГО до бара i (i-p … i-1). С текущим баром в окне
        # high_n >= close всегда, условие close > high_n недостижимо и стратегия
        # не входила ни разу. Отрицательный старт iloc завернул бы выборку в
        # конец ряда (заглядывание вперёд) — такие бары пропускаем.
        lo_i = i - p
        if lo_i < 0:
            continue
        high_n = df['high'].iloc[lo_i:i].max()
        low_n = df['low'].iloc[lo_i:i].min()
        
        # high_n / low_n — уже скаляры, алиасы high_val/low_val не нужны



        
        if df['close'].iloc[i] > high_n:
            k[i] = 1
        elif df['close'].iloc[i] < low_n:
            k[i] = -1
    
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
    return run_backtest(df, calc_chan_adaptive_donchian, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
