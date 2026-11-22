"""Mean Reversion: RSI + Vol Filter (H1).

Idea: 0886 mr_rsi_vol_filter
Вход: RSI < 25 и σ < p50 (не тренд, а флэт)
Выход: RSI > 50
Отличие: Фильтр волатильности — не входить в mean-reversion в реальном тренде
"""
import numpy as np
import pandas as pd


def calc_mr_rsi_vol_filter(df, param_key):
    """RSI < 25 при низкой волатильности."""
    parts = str(param_key).split(',') if isinstance(param_key, str) else [str(param_key)]
    rsi_period = int(parts[0]) if len(parts) > 0 else 14
    vol_period = int(parts[1]) if len(parts) > 1 else 50
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(rsi_period).mean()
    avg_loss = loss.rolling(rsi_period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    vol = df['close'].pct_change().rolling(vol_period).std()
    vol_threshold = vol.rolling(vol_period).apply(
        lambda x: np.percentile(x, 50) if len(x) > 10 else np.nan, raw=True
    )

    k = np.zeros(len(df))
    k[(rsi < 25) & (vol < vol_threshold)] = 1
    k[(rsi > 75) & (vol < vol_threshold)] = -1

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
    rsi_period = int(parts[0]) if len(parts) > 0 else 14
    vol_period = int(parts[1]) if len(parts) > 1 else 50
    # calc_mr_rsi_vol_filter сам разбирает param_key («rsi,vol»). Обёртка собирала
    # те же параметры вручную и звала его с тремя аргументами — TypeError на каждой
    # комбинации, и семейство молча выпадало через _safe_backtest.
    return calc_mr_rsi_vol_filter(df, param_key)


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
