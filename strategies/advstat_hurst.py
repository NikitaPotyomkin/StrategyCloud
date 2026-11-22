"""Advanced stat: Hurst exponent regime (идея ~0290).

Гипотеза: показатель Хёрста определяет режим рынка:
H > 0.5 — трендовый (следовать тренду)
H < 0.5 — mean-reverting (торговать отклонения)
H ~ 0.5 — случайное блуждание (не торговать)

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_hurst_exponent(df, period=60):
    """Приближённый показатель Хёрста через R/S анализ.
    
    returns: df с колонкой 'k' (hurst exponent)
    """
    returns = df['close'].pct_change().dropna()
    
    hurst_vals = []
    
    for i in range(len(returns)):
        if i < period:
            hurst_vals.append(0.5)
            continue
        
        window = returns.iloc[i - period:i].values
        
        # R/S анализ с lag=10
        lag = 10
        if i < lag + period:
            hurst_vals.append(0.5)
            continue
        
        # Среднее и variance
        mean_ret = np.mean(window)
        trend = window - mean_ret
        
        # Cumulative deviation from mean
        cum_dev = np.cumsum(trend)
        
        # Range
        r = np.max(cum_dev) - np.min(cum_dev)
        
        # Standard deviation
        s = np.std(window)
        
        if s < 1e-8 or r < 1e-8:
            hurst_vals.append(0.5)
            continue
        
        # R/S ratio
        rs_ratio = r / s
        
        # H ≈ log(R/S) / log(lag) для упрощённого подхода
        # Более точный: используем несколько lag и линейную регрессию
        # Но для скорости берём приближение
        h = np.log(rs_ratio + 1e-8) / np.log(lag + 1e-8)
        h = np.clip(h, 0.0, 1.0)  # Ограничение [0, 1]
        
        hurst_vals.append(h)
    
    # (right) reindex на df.index — иначе Length mismatch если len(returns) != len(df)
    hurst_series = pd.Series(hurst_vals, index=df.index[:len(hurst_vals)])
    df['k'] = hurst_series.reindex(df.index, fill_value=0.5)
    
    return df


def check_entry(prev, curr):
    """Вход при смене режима: H < 0.4 (mean-revert) или H > 0.6 (trend)."""
    return abs(prev) < 0.5 and abs(curr) > 0.55


def check_exit(prev, curr, direction):
    """Выход при возврате к случайности (H ~ 0.5)."""
    return abs(curr - 0.5) < 0.1


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
    """Бэктест на hurst exponent regime."""
    period = int(param_key) if param_key else 60
    return calc_hurst_exponent(df, period)


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
