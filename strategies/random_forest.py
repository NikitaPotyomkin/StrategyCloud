"""Стратегия Random Forest — вход по уверенности классификатора.

Walk-forward: модель переобучается каждые ``retrain_every`` баров, обучающая
выборка берётся ТОЛЬКО из прошлого (исключено заглядывание в будущее).
bfill удалён — он заполнял пропуски будущими значениями (data leakage).
"""
import numpy as np
import pandas as pd
import os

from config import RF_RETRAIN_EVERY

# ── Мемо walk-forward прогнозов ──
# rf_prob НЕ зависит от threshold: порог влияет только на rf_signal, а backtest сам
# считает rf_sig_thresh из rf_prob. Значит обучение модели не нужно повторять для каждого
# порога грида (RF_THRESHOLD_RANGE) — кэшируем прогноз по ключу
# (отпечаток df, lookback, n_bars, n_estimators, max_depth, retrain_every).
# id(df) в ключ НЕ входит: calc_random_forest_once сам делает df.copy() и make_features()
# (там ещё один copy) — каждый вызов получает СВЕЖИЙ объект, и с id(df) кэш не попадал бы.
# Откат: STRATEGYCLOUD_RF_MEMO=0.
RF_MEMO_PROB = os.environ.get('STRATEGYCLOUD_RF_MEMO', '1').strip().lower() not in ('0', 'false', 'no', 'off', '')
_PROB_CACHE = {}
_PROB_CACHE_MAX = 16


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


def _df_fingerprint(df):
    """Дешёвый отпечаток кадра для мемо: длина, границы индекса, последний close, хэш OHLC.

    Ловит правку НА МЕСТЕ (дописывание нового бара в тот же объект)."""
    try:
        n = len(df)
        if n == 0:
            return (0, None, None, None)
        cols = [c for c in ('high', 'low', 'close') if c in df.columns]
        blob = b''.join(np.ascontiguousarray(df[c].to_numpy(dtype=float)).tobytes()
                        for c in cols)
        return (n, df.index[0], df.index[-1], float(df['close'].iloc[-1]), hash(blob))
    except Exception:
        return None


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

    # Признаки и таргет один раз в numpy — walk-forward цикл больше не режет pandas
    # на каждой итерации. Значения те же, что дают df.iloc[…][feature_cols] и
    # df.iloc[…]['target'] (позиционные срезы), поэтому прогнозы не меняются.
    F = df[feature_cols].to_numpy(dtype=float)
    F_ok = ~np.isnan(F).any(axis=1)
    y_all = df['target'].to_numpy(dtype=float)
    # Мемо: тот же кадр/параметры модели → прогноз уже посчитан (threshold в ключ НЕ входит)
    memo_key = None
    prob = None
    if RF_MEMO_PROB:
        memo_key = (_df_fingerprint(df), int(lookback), int(n_bars),
                    int(n_estimators), int(max_depth), int(retrain_every))
        prob = _PROB_CACHE.get(memo_key)

    prob_cached = prob is not None
    if prob is None:
        prob = np.full(n, np.nan, dtype=float)

    while not prob_cached and start < n:
        # --- Обучение только на прошлом (без будущего) ---
        train_start = max(0, start - lookback)
        train_end = start - n_bars  # последняя строка с известным таргетом

        valid = F_ok[train_start:train_end] & ~np.isnan(y_all[train_start:train_end])
        X_valid = F[train_start:train_end][valid]
        y_valid = y_all[train_start:train_end][valid].astype(int)

        if len(X_valid) < 50 or len(np.unique(y_valid)) < 2:
            start += retrain_every
            continue

        model = train_model(X_valid, y_valid, n_estimators, max_depth)
        if model is None:
            start += retrain_every
            continue

        # --- Предсказание для баров [start, end) ---
        end = min(start + retrain_every, n)
        valid_pred = F_ok[start:end]

        if valid_pred.any():
            probs = model.predict_proba(F[start:end][valid_pred])[:, 1]
            prob[start:end][valid_pred] = probs

        start = end

    # Кладём копию, чтобы кадр/вызов не могли испортить закэшированный массив
    if RF_MEMO_PROB and memo_key is not None and not prob_cached:
        if len(_PROB_CACHE) >= _PROB_CACHE_MAX:
            _PROB_CACHE.clear()
        _PROB_CACHE[memo_key] = prob.copy()

    df['rf_prob'] = prob

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
    from strategies._bt_core import TradeList, trade_row  # v2: журнал сделок
    trade_profits = TradeList()

    # Предварительно считаем сигналы для данного threshold
    df_calc['rf_sig_thresh'] = 0
    df_calc.loc[df_calc['rf_prob'] >= threshold, 'rf_sig_thresh'] = 1
    df_calc.loc[df_calc['rf_prob'] <= (1 - threshold), 'rf_sig_thresh'] = -1

    _c_df_calc_rf_sig_thresh = df_calc['rf_sig_thresh'].to_numpy()   # numpy-петля: позиционный доступ
    _c_df_calc_close = df_calc['close'].to_numpy()   # numpy-петля: позиционный доступ
    _c_df_calc_high = df_calc['high'].to_numpy()   # numpy-петля: позиционный доступ
    _c_df_calc_low = df_calc['low'].to_numpy()   # numpy-петля: позиционный доступ
    for i in range(1, len(df_calc)):
        prev_signal = _c_df_calc_rf_sig_thresh[i - 1]
        curr_signal = _c_df_calc_rf_sig_thresh[i]
        curr_close = _c_df_calc_close[i]
        current_high = _c_df_calc_high[i]
        current_low = _c_df_calc_low[i]

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
                _row = trade_row(df.index, _entry_i, i, position["direction"], p)
                if _row is not None:
                    trade_profits.times.append(_row)
                position = None

        # ── Проверка входа ──
        if position is None:
            entry_dir = check_entry(prev_signal, curr_signal)
            if entry_dir == 'long':
                entry = curr_close + spread
                _entry_i = i
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close - spread
                _entry_i = i
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits


# Алиас для движка/live: main.py импортирует calc_random_forest
calc_random_forest = calc_random_forest_once
