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


def backtest(df, param_key, sl_points, tp_points, point, tick_value,
             tick_size, sim_lot=0.01, spread_points=0):
    parts = str(param_key).split(',') if isinstance(param_key, str) else [str(param_key)]
    rsi_period = int(parts[0]) if len(parts) > 0 else 14
    vol_period = int(parts[1]) if len(parts) > 1 else 50

    df = calc_mr_rsi_vol_filter(df, rsi_period, vol_period)
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
