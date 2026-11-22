"""Multi-indicator composite: ADX + RSI + MA (идея ~0262).

Гипотеза: сильный тренд (ADX > 25) + RSI в сторону тренда + цена выше MA
даёт надёжный сигнал продолжения.

H1 OHLC только. SL/TP в спредах символа.
"""
import numpy as np
import pandas as pd


def calc_adx_rsi_ma(df, adx_period=14, rsi_period=14, ma_period=50):
    """Композит тренд-фильтра.
    
    returns: df с колонкой 'k' (score -1..1)
    """
    # ADX
    delta_high = df['high'].diff()
    delta_low = df['low'].diff()
    
    plus_dm = delta_high.where((delta_high > delta_low) & (delta_high > 0), 0.0)
    minus_dm = delta_low.where((delta_low > delta_high) & (delta_low > 0), 0.0)
    
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['close'].shift()).abs()
    tr3 = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.rolling(adx_period).mean()
    plus_di = 100 * (plus_dm.rolling(adx_period).mean() / atr.replace(0, 1e-8))
    minus_di = 100 * (minus_dm.rolling(adx_period).mean() / atr.replace(0, 1e-8))
    
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-8)
    adx = dx.rolling(adx_period).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(rsi_period).mean()
    avg_loss = loss.rolling(rsi_period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # MA
    ma = df['close'].rolling(ma_period).mean()
    
    # Композит
    trend_up = (adx > 25) & (plus_di > minus_di) & (df['close'] > ma) & (rsi > 50)
    trend_down = (adx > 25) & (minus_di > plus_di) & (df['close'] < ma) & (rsi < 50)
    
    k = np.where(trend_up, 1.0, np.where(trend_down, -1.0, 0.0))
    
    # (right) k уже numpy array — присваиваем напрямую
    df['k'] = k
    
    return df


def check_entry(prev, curr):
    """Вход при появлении трендового сигнала."""
    return prev == 0.0 and curr != 0.0


def check_exit(prev, curr, direction):
    """Выход при исчезновении."""
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
    """Бэктест multi-indicator trend filter."""
    parts = str(param_key).split(',') if param_key else '14,14,50'
    adx_period = int(parts[0]) if len(parts) > 0 else 14
    rsi_period = int(parts[1]) if len(parts) > 1 else 14
    ma_period = int(parts[2]) if len(parts) > 2 else 50
    return calc_adx_rsi_ma(df, adx_period, rsi_period, ma_period)


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
