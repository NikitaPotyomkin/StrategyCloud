"""Mean Reversion: ADR Overshoot (H1).

Idea: 0887 mr_overshoot_range
Вход: пройдено > 130% ADR
Выход: возврат 30% хода
Отличие: Откат от экстремума относительно среднего дневного диапазона
"""
import numpy as np
import pandas as pd


def calc_mr_overshoot_range(df, param_key):
    """Цена > 130% ADR от open дня."""
    adr_period = int(param_key) if not isinstance(param_key, str) or ',' not in str(param_key) else 20
    # (right) ADR — средний диапазон за adr_period дней
    daily_range = df['high'] - df['low']
    adr = daily_range.rolling(adr_period).mean()

    # (right) open дня — берём open первого бара дня
    day_open = df['open'].groupby(df.index.date).transform('first')

    from_open = df['close'] - day_open
    overshoot_long = (from_open > 1.3 * adr)  # цена выше 130% ADR
    overshoot_short = (from_open < -1.3 * adr)  # цена ниже -130% ADR

    k = np.zeros(len(df))
    k[overshoot_long] = 1
    k[overshoot_short] = -1

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
    return run_backtest(df, calc_mr_overshoot_range, check_entry, check_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
