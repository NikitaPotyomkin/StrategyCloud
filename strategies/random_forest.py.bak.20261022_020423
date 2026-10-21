"""Стратегия Random Forest — вход по уверенности классификатора.

Walk-forward: модель переобучается каждые ``retrain_every`` баров, обучающая
выборка берётся ТОЛЬКО из прошлого (исключено заглядывание в будущее).
bfill удалён — он заполнял пропуски будущими значениями (data leakage).
"""
import numpy as np
import pandas as pd
from config import RF_RETRAIN_EVERY


def make_features(df, lookback):
    """Добавляет признаки для Random Forest в существующий DataFrame."""
    df = df.copy()
    returns = df['close'].pct_change()

    # Лаговые доходности
    max_lag = min(6, lookback)
    for lag in range(1, max_lag):
        df[f'ret_lag{lag}'] = returns.shift(lag)

    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))

    # ATR
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    # ATR %
    df['atr_pct'] = df['atr'] / df['close']

    # Размах high-low %
    df['hl_range'] = (df['high'] - df['low']) / df['close']

    # День недели
    df['dow'] = df.index.dayofweek

    # Только ffill (без bfill!) — не заполняем прошлое будущими значениями
    df = df.ffill().fillna(0)

    return df


def train_model(X, y, n_estimators=50, max_depth=5):
    """Обучает Random Forest (sklearn)."""
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError:
        return None

    model = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=42,
        n_jobs=1  # 1 ядро (параллелизм — на уровне процессов)
    )
    model.fit(X, y)
    return model


def calc_random_forest_once(df, lookback, n_bars, threshold=0.6,
                            n_estimators=50, max_depth=5, retrain_every=RF_RETRAIN_EVERY):
    """Считает признаки и прогнозами Walk-Forward Random Forest.

    Для каждого окна предсказаний [start, start+retrain_every) обучающая
    выборка — это [start-lookback, start-n_bars), где таргет (рост/падение
    через n_bars) уже известен. Это исключает заглядывание в будущее.

    Возвращает DataFrame с колонками 'rf_prob' и 'rf_signal'.
    """
    df = df.copy()
    if len(df) < lookback + n_bars + 30:
        df['rf_prob'] = np.nan
        df['rf_signal'] = 0
        return df

    # Целевая переменная (последние n_bars строк будут NaN — нормально)
    df['target'] = (df['close'].shift(-n_bars) > df['close']).astype(int)

    df = make_features(df, lookback)

    feature_prefixes = ('ret_lag', 'rsi', 'atr', 'hl_range', 'dow')
    feature_cols = [c for c in df.columns if c.startswith(feature_prefixes)]

    n = len(df)
    df['rf_prob'] = np.nan
    df['rf_signal'] = 0

    retrain_every = max(1, retrain_every)
    start = lookback + n_bars

    while start < n:
        # --- Обучение только на прошлом (без будущего) ---
        train_start = max(0, start - lookback)
        train_end = start - n_bars  # последняя строка с известным таргетом

        X_train = df.iloc[train_start:train_end][feature_cols]
        y_train = df.iloc[train_start:train_end]['target']

        valid = y_train.notna() & X_train.notna().all(axis=1)
        X_valid = X_train[valid].values
        y_valid = y_train[valid].values.astype(int)

        if len(X_valid) < 50 or len(np.unique(y_valid)) < 2:
            start += retrain_every
            continue

        model = train_model(X_valid, y_valid, n_estimators, max_depth)
        if model is None:
            start += retrain_every
            continue

        # --- Предсказание для баров [start, end) ---
        end = min(start + retrain_every, n)
        X_pred = df.iloc[start:end][feature_cols]
        valid_pred = X_pred.notna().all(axis=1)

        if valid_pred.any():
            probs = model.predict_proba(X_pred[valid_pred].values)[:, 1]
            pred_idx = X_pred.index[valid_pred]
            df.loc[pred_idx, 'rf_prob'] = probs

        start = end

    # --- Сигналы по порогу ---
    df.loc[df['rf_prob'] >= threshold, 'rf_signal'] = 1
    df.loc[df['rf_prob'] <= (1 - threshold), 'rf_signal'] = -1

    df = df.drop(columns=['target'], errors='ignore')
    return df


def check_entry(prev_signal, curr_signal):
    """Вход по смене сигнала."""
    if prev_signal == 0 and curr_signal == 1:
        return 'long'
    if prev_signal == 0 and curr_signal == -1:
        return 'short'
    return None


def check_exit(prev_signal, curr_signal, direction):
    """Выход при смене сигнала на противоположный."""
    if direction == 'long':
        return curr_signal == -1
    else:
        return curr_signal == 1


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, lookback, n_bars, threshold, sl_points, tp_points, point,
             tick_value, tick_size, n_estimators=50, max_depth=5,
             sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Random Forest (walk-forward).
    Перебираются только threshold, SL, TP.
    Возвращает (profit, n_trades, trade_profits).
    """
    # 1. Считаем признаки и walk-forward прогнозы
    df_calc = calc_random_forest_once(df, lookback, n_bars, threshold=threshold,
                                      n_estimators=n_estimators, max_depth=max_depth)

    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    # Предварительно считаем сигналы для данного threshold
    df_calc['rf_sig_thresh'] = 0
    df_calc.loc[df_calc['rf_prob'] >= threshold, 'rf_sig_thresh'] = 1
    df_calc.loc[df_calc['rf_prob'] <= (1 - threshold), 'rf_sig_thresh'] = -1

    for i in range(1, len(df_calc)):
        prev_signal = df_calc['rf_sig_thresh'].iloc[i - 1]
        curr_signal = df_calc['rf_sig_thresh'].iloc[i]
        curr_close = df_calc['close'].iloc[i]
        current_high = df_calc['high'].iloc[i]
        current_low = df_calc['low'].iloc[i]

        # ── Проверка выхода ──
        if position:
            exited = False
            p = 0.0
            d = position['direction']

            if d == 'long':
                if current_low <= position['sl']:
                    p = _profit(position['entry'], position['sl'], tick_value, tick_size, sim_lot, 'long')
                    exited = True
                elif current_high >= position['tp']:
                    p = _profit(position['entry'], position['tp'], tick_value, tick_size, sim_lot, 'long')
                    exited = True
                elif check_exit(prev_signal, curr_signal, 'long'):
                    p = _profit(position['entry'], curr_close, tick_value, tick_size, sim_lot, 'long')
                    exited = True
            else:
                if current_high >= position['sl']:
                    p = _profit(position['entry'], position['sl'], tick_value, tick_size, sim_lot, 'short')
                    exited = True
                elif current_low <= position['tp']:
                    p = _profit(position['entry'], position['tp'], tick_value, tick_size, sim_lot, 'short')
                    exited = True
                elif check_exit(prev_signal, curr_signal, 'short'):
                    p = _profit(position['entry'], curr_close, tick_value, tick_size, sim_lot, 'short')
                    exited = True

            if exited:
                p -= (spread / tick_size) * tick_value * sim_lot
                profit += p
                n_trades += 1
                trade_profits.append(p)
                position = None

        # ── Проверка входа ──
        if position is None:
            entry_dir = check_entry(prev_signal, curr_signal)
            if entry_dir == 'long':
                entry = curr_close + spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close - spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits


# Алиас для совместимости с check_active_signals
calc_random_forest = calc_random_forest_once
