"""Volatility Regime: Yang-Zhang Regime (H1).

Idea: 0004 volreg_yz_regime
Вход: Yang-Zhang(24) grows 3 bars + close > SMA50
Выход: opposite signal
Отличие: YZ-волатильность включает overnight gaps
"""
import numpy as np
import pandas as pd


def calc_volreg_yz_regime(df, period=24):
    """Yang-Zhang volatility regime detection."""
    o = np.log(df['open'])
    h = np.log(df['high'])
    l = np.log(df['low'])
    c = np.log(df['close'])
    
    # Overnight return variance
    overnight = (o - c.shift(1)) ** 2
    # Intraday return variance
    intraday = (h - l) ** 2
    # Close-to-close variance
    close_close = (c - c.shift(1)) ** 2
    
    # YZ decomposition
    n = len(df)
    yz_vol = pd.Series(0.0, index=df.index)
    
    for i in range(period, n):
        overnight_hist = overnight.iloc[i-period+1:i+1]
        intraday_hist = intraday.iloc[i-period+1:i+1]
        close_close_hist = close_close.iloc[i-period+1:i+1]

        sigma_overnight = overnight_hist.mean()
        sigma_intraday = intraday_hist.mean()
        sigma_close = close_close_hist.mean()

        # (right) Fix: renamed accumulator from sigma_overnight to sum_sq_diff
        # to avoid variable collision (sigma_overnight was being overwritten)
        # (right) Fix: iterate over actual window data, not range(period),
        # to prevent IndexError when window < period (i.e., i > 2*period-1)
        sum_sq_diff = 0.0
        for oh, ih, cc in zip(overnight_hist, intraday_hist, close_close_hist):
            sum_sq_diff += (oh + ih - sigma_close) ** 2

        yz = sigma_close + (1.0 / (period - 1)) * sum_sq_diff
        yz_vol.iloc[i] = yz ** 0.5
    
    sma50 = df['close'].rolling(50).mean()
    growing = (yz_vol > yz_vol.shift(1)) & (yz_vol > yz_vol.shift(2)) & (yz_vol > yz_vol.shift(3))
    
    k = np.zeros(len(df))
    k[(growing) & (df['close'] > sma50)] = 1
    k[(yz_vol < yz_vol.shift(1) * 0.8) & (df['close'] < sma50)] = -1
    
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
    return run_backtest(df, calc_volreg_yz_regime, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
