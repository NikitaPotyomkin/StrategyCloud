"""Advanced stat: Fractal Dimension regime (идея ~0292).

Гипотеза: фрактальная размерность Холла измеряет "сглаженность" тренда:
FD < 0.7 — сильный тренд (следовать)
FD > 1.3 — шум (не торговать)
0.7 < FD < 1.0 — слабый тренд (осторожно)

H1 OHLC только. SL/TP в пунктах символа (sl_points * point).
Спред в этой стратегии не моделируется — как и раньше; для сравнения семейств
это надо помнить (у большинства стратегий проекта spread_points учитывается).
"""
import numpy as np
import pandas as pd


def calc_fractal_dimension(df, period=20):
    """Фрактальная размерность Холла (Hurst-based).
    
    FD = 2 - H
    
    returns: df с колонкой 'k' (fractal dimension)
    """
    returns = df['close'].pct_change().dropna()
    
    fd_vals = []
    
    for i in range(len(returns)):
        if i < period:
            fd_vals.append(1.0)
            continue
        
        window = returns.iloc[i - period:i].values
        
        # Mean and standard deviation
        mean_ret = np.mean(window)
        std_ret = np.std(window)
        
        if std_ret < 1e-8:
            fd_vals.append(1.0)
            continue
        
        # Log return variance
        log_var = np.log(std_ret ** 2 + 1e-16)
        
        # H approximation через scaling
        # Используем simple R/S approach
        cum_dev = np.cumsum(window - mean_ret)
        r = np.max(cum_dev) - np.min(cum_dev)
        s = std_ret * np.sqrt(period)
        
        if s < 1e-8 or r < 1e-8:
            fd_vals.append(1.0)
            continue
        
        rs_ratio = r / s
        h = np.log(rs_ratio + 1e-16) / np.log(np.sqrt(period) + 1e-16)
        h = np.clip(h, 0.0, 1.0)
        
        # FD = 2 - H
        fd = 2.0 - h
        
        fd_vals.append(fd)
    
    # ВАЖНО: pct_change().dropna() короче df ровно на одну строку (первая),
    # поэтому len(fd_vals) = len(df) - 1. Прямое df['k'] = np.array(fd_vals)
    # падало с "Length of values (1456) does not match length of index (1457)"
    # и семейство выпадало из чекпойнта без журналов сделок.
    df['k'] = np.concatenate(([1.0], np.asarray(fd_vals, dtype=float)))
    
    return df


def check_entry(prev, curr):
    """Вход при сильном тренде (curr < 0.8)."""
    return prev > 0.8 and curr < 0.8


def check_exit(prev, curr, direction):
    """Выход при росте шума (curr > 1.3)."""
    return curr > 1.3


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
    """Бэктест на fractal dimension."""
    period = int(param_key) if param_key else 20
    return calc_fractal_dimension(df, period)


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
