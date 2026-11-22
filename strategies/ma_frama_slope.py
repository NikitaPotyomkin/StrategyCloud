"""MA: FRAMA Slope (H1).

Idea: 0243 ma_frama_slope
Вход: FRAMA slope > thr
Выход: slope < 0
Отличие: Fractal Adaptive Moving Average
"""
import numpy as np
import pandas as pd


def calc_ma_frama_slope(df, period=16):
    change = abs(df['close'] - df['close'].shift(period))
    vol = df['close'].diff().abs().rolling(period).sum()
    er = change / vol.replace(0, np.nan)
    alpha = er ** 2
    
    frama = df['close'].copy()
    for i in range(period, len(df)):
        frama.iloc[i] = alpha.iloc[i] * df['close'].iloc[i] + (1 - alpha.iloc[i]) * frama.iloc[i-1]
    
    slope = frama.diff(period)
    
    k = np.zeros(len(df))
    k[slope > 0] = 1
    k[slope < 0] = -1
    
    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    # k здесь двузначный (только ±1): нулевого состояния после прогрева нет,
    # поэтому prev == 0 не наступает никогда и стратегия не входила вовсе.
    # Вход по СМЕНЕ состояния — как в _bt_core.state_entry / живом движке.
    if curr == 1 and prev != 1:
        return 'long'
    if curr == -1 and prev != -1:
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
    return run_backtest(df, calc_ma_frama_slope, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
