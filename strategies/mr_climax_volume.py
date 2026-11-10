"""Mean Reversion: Climax Volume (H1).

Idea: 0893 mr_climax_volume
Вход: объём > p95 и цена у экстремума → fade
Выход: 5 баров
Отличие: Свечной экстремум + всплеск объёма = финальный штурм
"""
import numpy as np
import pandas as pd


def calc_mr_climax_volume(df, vol_period=200, ext_period=20):
    """Объём > p95 на экстремуме 20 баров."""
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
    return (prev == 0 and curr == 1) or (prev == 0 and curr == -1)


def check_exit(prev, curr, direction):
    if direction == 'long' and curr <= 0:
        return True
    if direction == 'short' and curr >= 0:
        return True
    return False


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    df = calc_mr_climax_volume(df, int(param_key))
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
