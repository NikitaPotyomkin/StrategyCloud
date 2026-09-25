"""Стратегия Logistic Regression — прогноз направления через N баров.

Ядро: (symbol, 'logreg', lookback, n_bars, threshold)
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression as SklearnLogisticRegression
from strategies.base import BaseStrategy


class LogisticRegression(BaseStrategy):
    """Логистическая регрессия: вход при уверенности модели > порога."""

    name = 'logreg'

    def _make_features(self, df, lookback=100, n_bars=12, threshold=0.55):
        """Создаёт признаки для логистической регрессии."""
        df = df.copy()
        returns = df['close'].pct_change()

        for lag in range(1, min(7, lookback)):
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
        df['atr_pct'] = df['atr'] / df['close']

        df['hl_range'] = (df['high'] - df['low']) / df['close']

        if 'volume' in df.columns:
            df['vol_ma'] = df['volume'].rolling(14).mean()
            df['vol_ratio'] = df['volume'] / df['vol_ma'].replace(0, np.nan)

        df['dow'] = df.index.dayofweek

        df = df.bfill().ffill().fillna(0)
        return df

    def calc_indicator(self, df, lookback=100, n_bars=12, threshold=0.55, retrain_every=100):
        """Рассчитывает сигналы Logistic Regression.

        Модель обучается ОДИН РАЗ на всём окне lookback..end,
        затем predict_proba применяется векторизованно ко всем строкам.
        """
        df = self._make_features(df, lookback, n_bars, threshold)
        df['lr_prob'] = np.nan
        df['lr_signal'] = 0

        if len(df) < lookback + n_bars + 30:
            return df

        feature_cols = [c for c in df.columns
                        if c.startswith(('ret_lag', 'rsi', 'atr', 'hl_range', 'dow', 'vol'))]

        # ── Обучаем модель ОДИН РАЗ на всём окне ──
        # Берём стартовый срез [0:lookback] как обучающую выборку.
        # Целевая переменная: вырастет ли цена через n_bars.
        train_end = lookback
        X_train = df.iloc[:train_end][feature_cols].values
        y_train = (df['close'].iloc[:train_end].shift(-n_bars)
                   > df['close'].iloc[:train_end]).astype(int)

        # Убираем строки с NaN-таргетом (последние n_bars строк обучающей выборки)
        valid_mask = np.isfinite(y_train) & np.isfinite(X_train).all(axis=1)
        X_valid = X_train[valid_mask]
        y_valid = y_train[valid_mask]

        if len(X_valid) < 30 or len(np.unique(y_valid)) < 2:
            return df

        model = SklearnLogisticRegression(
            C=1.0, max_iter=1000, random_state=42, class_weight='balanced',n_jobs=1
        )
        model.fit(X_valid, y_valid)

        # ── Векторизованный predict_proba для всех строк ──
        X_all = df[feature_cols].values
        valid_all = np.isfinite(X_all).all(axis=1)
        probs = np.full(len(df), np.nan)
        if valid_all.any():
            probs[valid_all] = model.predict_proba(X_all[valid_all])[:, 1]

        df['lr_prob'] = probs

        # Сигналы по порогу
        df.loc[df['lr_prob'] >= threshold, 'lr_signal'] = 1
        df.loc[df['lr_prob'] <= (1 - threshold), 'lr_signal'] = -1

        return df

    def check_entry(self, prev_signal, curr_signal):
        if prev_signal == 0 and curr_signal == 1:
            return 'long'
        if prev_signal == 0 and curr_signal == -1:
            return 'short'
        return None

    def check_exit(self, prev_signal, curr_signal, direction):
        if direction == 'long':
            return curr_signal == -1
        return curr_signal == 1


# ── Кэш обученных моделей: (symbol, lookback, n_bars) -> вероятности ──
# Если run_full_backtest вызывает calc_logreg несколько раз для одного
# символа с разными threshold/SL/TP, мы не переобучаем модель.
_lr_cache = {}


def _calc_logreg_cached(df, lookback, n_bars, threshold):
    """Считает lr_prob один раз на (lookback, n_bars), кэширует результат."""
    cache_key = (id(df), lookback, n_bars)
    if cache_key in _lr_cache:
        cached = _lr_cache[cache_key]
    else:
        strat = LogisticRegression()
        # Обучаем с любым threshold — он влияет только на сигнал, не на модель
        cached = strat.calc_indicator(df, lookback, n_bars, threshold=0.5)
        _lr_cache[cache_key] = cached
        # Чистим кэш, если он разросся
        if len(_lr_cache) > 50:
            _lr_cache.clear()
    return cached


def calc_logreg(df, lookback, n_bars, threshold, retrain_every=100):
    """Обёртка для check_active_signals (в реальном времени, без кэша)."""
    return LogisticRegression().calc_indicator(df, lookback, n_bars, threshold, retrain_every)


def check_entry(prev_signal, curr_signal):
    return LogisticRegression().check_entry(prev_signal, curr_signal)


def check_exit(prev_signal, curr_signal, direction):
    if direction == 'long':
        return curr_signal == -1
    return curr_signal == 1


def backtest(df, lookback, n_bars, threshold, sl_points, tp_points, point,
             tick_value, tick_size, retrain_every=100, sim_lot=0.01, spread_points=0):
    """Симуляция сделок на истории с Logistic Regression.

    Использует кэш: модель обучается один раз на (lookback, n_bars),
    а перебор threshold/SL/TP не вызывает переобучения.
    """
    # Используем кэшированную версию — модель обучается один раз
    df = _calc_logreg_cached(df, lookback, n_bars, threshold)

    # Пересчитываем сигналы под текущий threshold
    df = df.copy()
    df['lr_signal'] = 0
    df.loc[df['lr_prob'] >= threshold, 'lr_signal'] = 1
    df.loc[df['lr_prob'] <= (1 - threshold), 'lr_signal'] = -1

    strat = LogisticRegression()
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['lr_signal'].iloc[i - 1]
        curr_signal = df['lr_signal'].iloc[i]
        curr_close = df['close'].iloc[i]
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]

        if position:
            exited = False
            p = 0.0
            d = position['direction']

            if d == 'long':
                if current_low <= position['sl']:
                    p = strat.profit_rub(position['entry'], position['sl'], tick_value, tick_size, sim_lot, 'long')
                    exited = True
                elif current_high >= position['tp']:
                    p = strat.profit_rub(position['entry'], position['tp'], tick_value, tick_size, sim_lot, 'long')
                    exited = True
                elif strat.check_exit(prev_signal, curr_signal, 'long'):
                    p = strat.profit_rub(position['entry'], curr_close, tick_value, tick_size, sim_lot, 'long')
                    exited = True
            else:
                if current_high >= position['sl']:
                    p = strat.profit_rub(position['entry'], position['sl'], tick_value, tick_size, sim_lot, 'short')
                    exited = True
                elif current_low <= position['tp']:
                    p = strat.profit_rub(position['entry'], position['tp'], tick_value, tick_size, sim_lot, 'short')
                    exited = True
                elif strat.check_exit(prev_signal, curr_signal, 'short'):
                    p = strat.profit_rub(position['entry'], curr_close, tick_value, tick_size, sim_lot, 'short')
                    exited = True

            if exited:
                p -= (spread / tick_size) * tick_value * sim_lot
                profit += p
                n_trades += 1
                trade_profits.append(p)
                position = None

        if position is None:
            entry_dir = strat.check_entry(prev_signal, curr_signal)
            if entry_dir == 'long':
                entry = curr_close + spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close - spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
