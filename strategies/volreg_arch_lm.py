"""Volatility Regulation: ARCH LM Test (H1).

Idea: 0018 volreg_arch_lm
Вход: тест ARCH-LM обнаруживает кластеризацию волатильности.
     Высокая статистика ARCH-LM → волатильность кластеризуется → вход в пробой.
Выход: ARCH-LM падает ниже порога.
Отличие: статистический тест на гетероскедастичность (Engle, 1982).

Правка 12.11.2026: SL/TP >= 10 спредов, горизонт 8-24 бара.
"""
import numpy as np
import pandas as pd

from strategies._bt_core import run_backtest, state_entry, state_exit


def calc_volreg_arch_lm(df, period=50, lag=5, threshold=3.84):
    """ARCH LM test для обнаружения кластеризации волатильности.
    
    Тест Engle's ARCH LM:
    1. Регрессируем |r_t| на |r_{t-1}| ... |r_{t-lag}|
    2. R² * n ~ χ²(lag) под H0 (нет ARCH)
    3. Если R²*n > threshold → кластеризация волатильности
    
    returns: df с колонкой 'k' (-1, 0, 1)
    """
    returns = df['close'].pct_change().dropna()
    n = len(returns)
    
    # Заполняем NaN нулями
    returns = returns.fillna(0)
    
    k = np.zeros(n)
    
    for i in range(period + lag, n):
        # Абсолютные доходности
        abs_ret = returns.iloc[i - period - lag:i + 1].abs().values
        
        # Регрессия |r_t| на константу и lag лагов |r_{t-j}|
        X = np.ones((period, lag + 1))
        for j in range(1, lag + 1):
            X[:, j] = abs_ret[:-j]
        
        y = abs_ret[lag:]
        
        try:
            # OLS: β = (X'X)^{-1} X'y
            XtX = X.T @ X
            Xty = X.T @ y
            
            # Добавляем регуляризацию для устойчивости
            beta = np.linalg.solve(XtX + 1e-8 * np.eye(lag + 1), Xty)
            
            # Предсказания и R²
            y_pred = X @ beta
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            
            if ss_tot < 1e-12:
                continue
            
            r_squared = 1.0 - ss_res / ss_tot
            
            # LM статистика
            lm_stat = r_squared * period
            
            # Решаем по threshold (χ²(lag) при α=0.05)
            if lm_stat > threshold:
                # Кластеризация есть — входим в сторону текущего тренда
                curr_ret = returns.iloc[i]
                if curr_ret > 0:
                    k[i] = 1
                else:
                    k[i] = -1
        except np.linalg.LinAlgError:
            continue
    
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


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    return run_backtest(df, calc_volreg_arch_lm, state_entry, state_exit,
                        int(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
