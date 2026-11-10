"""Oscillator: Trend Intensity Index (H1).

Idea: 0331 osc_tii
Вход: TII > 70 (сильный тренд вверх)
Выход: TII < 30
Отличие: Индекс интенсивности тренда по знаковым барам
"""
import numpy as np
import pandas as pd


def calc_osc_tii(df, period=60):
    """Trend Intensity Index — отношение трендовых баров к общему диапазону."""
    # (right) используем rolling sum для подсчёта баров, закрывающихся выше open
    up_vol = df.where(df['close'] > df['open'], 0)['volume'] if 'volume' in df.columns else pd.Series(0, index=df.index)
    down_vol = df.where(df['close'] < df['open'], 0)['volume'] if 'volume' in df.columns else pd.Series(0, index=df.index)

    # (right) fillna для пустых значений
    up_vol = up_vol.fillna(0)
    down_vol = down_vol.fillna(0)

    total_vol = up_vol + down_vol + 1e-12
    tii = 100 * (up_vol.rolling(period).sum() - down_vol.rolling(period).sum()) / (total_vol.rolling(period).sum() + 1e-12)

    k = np.zeros(len(df))
    k[tii > 70] = 1
    k[tii < -70] = -1

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
    df = calc_osc_tii(df, int(param_key))
    profit = 0
    n_trades = 0
    trade_profits = []
    sl_dist = sl_points * point
    tp_dist = tp_points * point

    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        close = df['close'].iloc[i]
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]

        if prev_k == 0 and curr_k == 1:
            entry = close
            sl_price = entry - sl_dist
            tp_price = entry + tp_dist
            for j in range(i+1, min(i+50, len(df))):
                if df['low'].iloc[j] <= sl_price:
                    profit += (sl_price - entry) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(sl_price - entry)
                    break
                elif df['high'].iloc[j] >= tp_price:
                    profit += (tp_price - entry) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(tp_price - entry)
                    break
        elif prev_k == 0 and curr_k == -1:
            entry = close
            sl_price = entry + sl_dist
            tp_price = entry - tp_dist
            for j in range(i+1, min(i+50, len(df))):
                if df['high'].iloc[j] >= sl_price:
                    profit += (entry - sl_price) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(entry - sl_price)
                    break
                elif df['low'].iloc[j] <= tp_price:
                    profit += (entry - tp_price) * sim_lot * tick_value
                    n_trades += 1
                    trade_profits.append(entry - tp_price)
                    break

    return (profit, n_trades, trade_profits)
