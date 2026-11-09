"""Volume: Volume Imbalance (H1).

Idea: 0091 volprof_vol_imbalance
Вход: vol up-bars / down-bars > 1.5 (long), < 0.67 (short)
Выход: ratio вернулся в коридор (check_exit), плюс SL/TP.
Отличие: Volume direction imbalance.

Правка 10.11.2026: логика сигнала не менялась, бэктест переведён на общий
движок strategies._bt_core — вход по open следующего бара, учёт спреда,
выход по сигналу (раньше выход был только по SL/TP, а сделки, не дошедшие до
них за 50 баров, выпадали из статистики).
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_volprof_vol_imbalance(df, period=20):
    vol = df['volume'] if 'volume' in df.columns else pd.Series(1, index=df.index)
    up_vol = vol * (df['close'] > df['open']).astype(int)
    down_vol = vol * (df['close'] < df['open']).astype(int)

    up_sum = up_vol.rolling(period).sum()
    down_sum = down_vol.rolling(period).sum()

    imbalance = up_sum / down_sum.replace(0, np.nan)

    k = np.zeros(len(df))
    k[imbalance > 1.5] = 1
    k[imbalance < 0.67] = -1

    df = df.copy()
    df['k'] = k
    return df


def check_entry(prev, curr):
    return (prev == 0 and curr == 1) or (prev == 0 and curr == -1)


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    return run_backtest(df, calc_volprof_vol_imbalance, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
