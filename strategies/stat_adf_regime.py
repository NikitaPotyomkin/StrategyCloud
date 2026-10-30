"""Statistical: ADF Regime (H1).

Idea: 0481 stat_adf_regime
Вход: ADF p-value(120) < 0.05 → mean-reversion
Выход: p > 0.2
Отличие: Augmented Dickey-Fuller test for stationarity
"""
import numpy as np
import pandas as pd


def calc_stat_adf_regime(df, period=120):
    ret = df['close'].pct_change()
    
    lag = min(10, period // 10)
    delta_ret = ret.diff()
    lags = pd.concat([delta_ret, ret.shift(1).rolling(lag+1).apply(lambda x: x[:-1])], axis=1).dropna()
    
    y = lags.iloc[:, -1]
    X = lags.iloc[:, :-1]
    X = pd.concat([pd.Series(1, index=X.index), X], axis=1)
    
    beta = np.zeros(len(df))
    p_value = np.zeros(len(df))
    
    for i in range(period, len(df)):
        y_i = y.iloc[i-period:i]
        X_i = X.iloc[i-period:i]
        
        try:
            beta_i = np.linalg.inv(X_i.T @ X_i) @ X_i.T @ y_i
            residuals = y_i - X_i @ beta_i
            se = np.sqrt(np.sum(residuals**2) / (period - 2) / (X_i.T @ X_i).iloc[0, 0])
            t_stat = beta_i[0] / se if se > 0 else 0
            p_value[i] = 2 * (1 - min(abs(t_stat) / 2, 1))
            
            if p_value[i] < 0.05:
                beta[i] = -1  # mean-reversion
            else:
                beta[i] = 1  # trend
        except:
            beta[i] = 0
    
    k = beta[period:]
    
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
    df = calc_stat_adf_regime(df, int(param_key))
    
    profit = 0
    n_trades = 0
    trade_profits = []
    
    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i-1]
        curr_k = df['k'].iloc[i]
        
        sl = sl_points[0]
        tp = tp_points[0]

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
