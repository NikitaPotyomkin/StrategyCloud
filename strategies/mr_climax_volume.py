"""Mean Reversion: Climax Volume (H1).

Idea: 0893 mr_climax_volume
Вход: объём > p95 и цена у экстремума → fade
Выход: 5 баров
Отличие: Свечной экстремум + всплеск объёма = финальный штурм
"""
import numpy as np
import pandas as pd


def calc_mr_climax_volume(df, param_key):
    """Объём > p95 на экстремуме 20 баров."""
    parts = str(param_key).split(',') if isinstance(param_key, str) else [str(param_key)]
    vol_period = int(parts[0]) if len(parts) > 0 else 200
    ext_period = int(parts[1]) if len(parts) > 1 else 20
    vol = df['volume'] if 'volume' in df.columns else pd.Series(1, index=df.index)
    vol = vol.fillna(1)
    vol_p95 = vol.rolling(vol_period).apply(
        lambda x: np.percentile(x, 95) if len(x) > 10 else np.nan, raw=True
    )

    high_ext = df['high'].rolling(ext_period).max()
    low_ext = df['low'].rolling(ext_period).min()

    # (right) цена у экстремума — close в верхних 10% бара
    upper_close = (df['close'] - df['low']) / (df['high'] - df['low'] + 1e-12) > 0.9
    lower_close = (df['high'] - df['close']) / (df['high'] - df['low'] + 1e-12) > 0.9

    k = np.zeros(len(df))
    k[(vol > vol_p95) & (df['high'] >= high_ext) & upper_close] = 1    # штурм вверх
    k[(vol > vol_p95) & (df['low'] <= low_ext) & lower_close] = -1     # штурм вниз

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
    return run_backtest(df, calc_mr_climax_volume, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
