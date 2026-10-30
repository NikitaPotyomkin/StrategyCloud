"""Channel: Adaptive Donchian (H1).

Idea: 0201 chan_adaptive_donchian
Вход: breakout Donchian with period = round(20/ER)
Выход: opposite boundary
Отличие: Adaptive period based on Efficiency Ratio
"""
import numpy as np
import pandas as pd


def calc_chan_adaptive_donchian(df, period=20):
    change = abs(df['close'] - df['close'].shift(period))
    vol = df['close'].diff().abs().rolling(period).sum()
    er = change / vol.replace(0, np.nan)
    
    # NaN на прогреве (первые `period` баров) и при нулевой волатильности:
    # astype(int) на NaN падал ValueError → нейтральное значение = period.
    adaptive_period = (20 / er).fillna(period).round().clip(5, 60).astype(int)
    
    k = np.zeros(len(df))
    for i in range(period, len(df)):
        p = int(adaptive_period.iloc[i])
        # Окно Donchian — СТРОГО до бара i (i-p … i-1). С текущим баром в окне
        # high_n >= close всегда, условие close > high_n недостижимо и стратегия
        # не входила ни разу. Отрицательный старт iloc завернул бы выборку в
        # конец ряда (заглядывание вперёд) — такие бары пропускаем.
        lo_i = i - p
        if lo_i < 0:
            continue
        high_n = df['high'].iloc[lo_i:i].max()
        low_n = df['low'].iloc[lo_i:i].min()
        
        # high_n / low_n — уже скаляры, алиасы high_val/low_val не нужны



        
        if df['close'].iloc[i] > high_n:
            k[i] = 1
        elif df['close'].iloc[i] < low_n:
            k[i] = -1
    
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
    df = calc_chan_adaptive_donchian(df, int(param_key))
    
    profit = 0
    n_trades = 0
    trade_profits = []
    
    sl = sl_points[0]
    tp = tp_points[0]
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        
        if prev_k == 0 and curr_k == 1:
            sl_price = df['close'].iloc[i] - sl * point
            tp_price = df['close'].iloc[i] + tp * point
            for j in range(i+1, min(i+50, len(df))):
                if df['low'].iloc[j] <= sl_price:
                    profit += (sl_price - df['close'].iloc[i]) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(sl_price - df['close'].iloc[i])
                    break
                elif df['high'].iloc[j] >= tp_price:
                    profit += (tp_price - df['close'].iloc[i]) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(tp_price - df['close'].iloc[i])
                    break
                    
        elif prev_k == 0 and curr_k == -1:
            sl_price = df['close'].iloc[i] + sl * point
            tp_price = df['close'].iloc[i] - tp * point
            for j in range(i+1, min(i+50, len(df))):
                if df['high'].iloc[j] >= sl_price:
                    profit += (df['close'].iloc[i] - sl_price) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(df['close'].iloc[i] - sl_price)
                    break
                elif df['low'].iloc[j] <= tp_price:
                    profit += (df['close'].iloc[i] - tp_price) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(df['close'].iloc[i] - tp_price)
                    break
    
    return (profit, n_trades, trade_profits)
