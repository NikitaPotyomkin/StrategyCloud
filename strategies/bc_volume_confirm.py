"""Breakout continuation на объёмном подтверждении (идея ~0212).

Гипотеза: пробой диапазона с объёмом > p80 надёжнее ведёт к продолжению.
Без объёма — ложный пробой.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_volume_breakout(df, range_period=20, vol_period=60, vol_pct=80):
    """Пробой диапазона с объёмным фильтром.
    
    returns: df с колонкой 'k' (объёмный пробой = 1, иначе 0)
    """
    # Диапазон
    high_range = df['high'].rolling(range_period).max()
    low_range = df['low'].rolling(range_period).min()
    
    # Объём в перцентилях
    vol_pctile = df['volume'].rolling(vol_period).rank(pct=True)
    
    # Пробой + объём
    k = np.where(
        (df['close'] > high_range) & (vol_pctile > vol_pct / 100.0),
        1.0,
        np.where(
            (df['close'] < low_range) & (vol_pctile > vol_pct / 100.0),
            -1.0,
            0.0
        )
    )
    
    df['k'] = k
    
    return df


def check_entry(prev, curr):
    """Вход при появлении сигнала пробоя (curr != 0)."""
    return prev == 0.0 and curr != 0.0


def check_exit(prev, curr, direction):
    """Выход при исчезновении сигнала (curr == 0)."""
    return curr == 0.0


from strategies._bt_core import run_backtest
def _entry(prev, curr):
    """check_entry модуля отдаёт bool — направление берём из знака состояния.

    Прежняя петля входила в long при переходе 0→+1 и в short при 0→−1, а
    run_backtest ждёт 'long'/'short'/None. Булев ответ разворачиваем по curr.
    """
    if not check_entry(prev, curr):
        return None
    if curr == 1:
        return 'long'
    if curr == -1:
        return 'short'
    return None


def _calc(df, param_key):
    """calc_* с параметрами, собранными из param_key."""
    """Бэктест breakout continuation с объёмным фильтром."""
    param_key_str = str(param_key).split(',')[0] if isinstance(param_key, list) else str(param_key or '20,60,80')
    parts = param_key_str.split(',')
    range_period = int(parts[0]) if len(parts) > 0 else 20
    vol_period = int(parts[1]) if len(parts) > 1 else 60
    vol_pct = int(parts[2]) if len(parts) > 2 else 80
    return calc_volume_breakout(df, range_period, vol_period, vol_pct)


def backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """Симуляция через общий движок strategies/_bt_core.run_backtest.

    Вход по open следующего бара ± спред, спред вычитается и на выходе, обрыва
    по времени нет, деньги через trade_profit (÷ tick_size). Прежняя петля
    входила по close сигнального бара, не вычитала спред, выбрасывала сделки,
    не закрывшиеся за 49 баров, и считала P&L без деления на tick_size —
    из-за этого её числа были несравнимы с остальным реестром.
    """
    return run_backtest(df, _calc, _entry, check_exit,
                        param_key, sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
