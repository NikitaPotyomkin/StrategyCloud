"""АлисаОк Стратегия Logistic Regression — прогноз направления через N баров.

Ядро: (symbol, 'logreg', lookback, n_bars, threshold)

Основные отличия от исходной версии:
- Модель обучается в скользящем окне (walk-forward): для каждого окна
  [start, start+retrain_every) обучающая выборка — данные из диапазона
  [start-lookback, start-n_bars). Это исключает заглядывание в будущее.
- Кэш ключа включает retrain_every.
- bfill убран — он заполнял пропуски будущими значениями (data leakage).
- inf-значения заменяются на 0.
- Нулевые sl_points/tp_points обрабатываются как «нет стопа» (бесконечность).
- Добавлен параметр commission_per_lot.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression as SklearnLogisticRegression
from strategies.base import BaseStrategy


class LogisticRegression(BaseStrategy):
    """Логистическая регрессия: вход при уверенности модели > порога."""

    name = 'logreg'

    # ------------------------------------------------------------------ #
    #  Признаки
    # ------------------------------------------------------------------ #
    def _make_features(self, df, lookback=100):
        """Создаёт признаки для логистической регрессии.

        Использует только ffill (без bfill), чтобы не заполнять
        первые строки будущими значениями.
        """
        df = df.copy()
        returns = df['close'].pct_change()

        n_lags = min(7, lookback)
        for lag in range(1, n_lags):
            df[f'ret_lag{lag}'] = returns.shift(lag)

        # --- RSI(14) ---
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi'] = 100 - (100 / (1 + rs))

        # --- ATR(14) ---
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        df['atr_pct'] = df['atr'] / df['close']

        # --- High-Low range ---
        df['hl_range'] = (df['high'] - df['low']) / df['close']

        # --- Volume ---
        if 'volume' in df.columns:
            df['vol_ma'] = df['volume'].rolling(14).mean()
            df['vol_ratio'] = df['volume'] / df['vol_ma'].replace(0, np.nan)

        # --- Day of week ---
        df['dow'] = df.index.dayofweek

        # Только ffill — без bfill, чтобы не использовать будущие данные.
        # inf (возможен при делении на ~0 в RSI/ATR) — заменяем на 0.
        df = df.ffill().fillna(0)
        df = df.replace([np.inf, -np.inf], 0)
        return df

    def _get_feature_cols(self, df):
        """Возвращает список колонок-признаков."""
        return [c for c in df.columns
                if c.startswith(('ret_lag', 'rsi', 'atr',
                                 'hl_range', 'dow', 'vol'))]

    # ------------------------------------------------------------------ #
    #  Расчёт индикатора (walk-forward)
    # ------------------------------------------------------------------ #
    def calc_indicator(self, df, lookback=100, n_bars=12,
                       threshold=0.55, retrain_every=100):
        """Рассчитывает сигналы Logistic Regression.

        Walk-forward: модель переобучается каждые ``retrain_every`` баров.
        Для каждого окна предсказаний [start, start+retrain_every)
        обучающая выборка — это [start-lookback, start-n_bars),
        где таргет (рост/падение через n_bars) уже известен.
        Это полностью исключает заглядывание в будущее.
        """
        retrain_every = max(1, retrain_every)
        df = self._make_features(df, lookback=lookback)
        n = len(df)

        df['lr_prob'] = np.nan
        df['lr_signal'] = 0

        if n < lookback + n_bars + 30:
            return df

        feature_cols = self._get_feature_cols(df)

        # Таргет: вырастет ли цена через n_bars.
        # Для строки i таргет требует close[i + n_bars], поэтому
        # последние n_bars строк будут NaN — это нормально.
        target = (df['close'].shift(-n_bars) > df['close']).astype(float)

        start = lookback + n_bars

        while start < n:
            # --- Обучение ---
            # train_end = start - n_bars (exclusive):
            # последняя строка с известным таргетом — start - n_bars - 1.
            train_start = max(0, start - lookback)
            train_end = start - n_bars

            X_train = df.iloc[train_start:train_end][feature_cols]
            y_train = target.iloc[train_start:train_end]

            valid_mask = y_train.notna() & X_train.notna().all(axis=1)
            X_valid = X_train[valid_mask].values
            y_valid = y_train[valid_mask].values.astype(int)

            if len(X_valid) < 30 or len(np.unique(y_valid)) < 2:
                start += retrain_every
                continue

            model = SklearnLogisticRegression(
                C=1.0, max_iter=1000, random_state=42,
                class_weight='balanced', n_jobs=1,
            )
            model.fit(X_valid, y_valid)

            # --- Предсказание для баров [start, end) ---
            end = min(start + retrain_every, n)
            X_pred_df = df.iloc[start:end][feature_cols]
            valid_pred = X_pred_df.notna().all(axis=1)

            if valid_pred.any():
                probs = model.predict_proba(
                    X_pred_df[valid_pred].values
                )[:, 1]
                pred_idx = X_pred_df.index[valid_pred]
                df.loc[pred_idx, 'lr_prob'] = probs

            start = end

        # --- Сигналы по порогу ---
        df.loc[df['lr_prob'] >= threshold, 'lr_signal'] = 1
        df.loc[df['lr_prob'] <= (1 - threshold), 'lr_signal'] = -1

        return df

    # ------------------------------------------------------------------ #
    #  Вход / выход
    # ------------------------------------------------------------------ #
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


# ====================================================================== #
#  Кэш вероятностей
# ====================================================================== #
_lr_cache = {}


def _calc_logreg_cached(df, lookback, n_bars, threshold, retrain_every=100):
    """Считает lr_prob один раз на (lookback, n_bars, retrain_every).

    Кэширует DataFrame с колонкой lr_prob.
    Порог threshold на обучение не влияет — он применяется позже
    при пересчёте сигналов в backtest().
    """
    cache_key = (id(df), lookback, n_bars, retrain_every)
    if cache_key in _lr_cache:
        return _lr_cache[cache_key]

    strat = LogisticRegression()
    cached = strat.calc_indicator(
        df, lookback, n_bars, threshold=0.5, retrain_every=retrain_every,
    )
    _lr_cache[cache_key] = cached

    if len(_lr_cache) > 50:
        _lr_cache.clear()

    return cached


def clear_cache():
    """Очищает кэш обученных моделей."""
    _lr_cache.clear()


# ====================================================================== #
#  Обёртки для совместимости с фреймворком
# ====================================================================== #
def calc_logreg(df, lookback, n_bars, threshold, retrain_every=100):
    """Обёртка для check_active_signals (в реальном времени, без кэша)."""
    return LogisticRegression().calc_indicator(
        df, lookback, n_bars, threshold, retrain_every,
    )


def check_entry(prev_signal, curr_signal):
    return LogisticRegression().check_entry(prev_signal, curr_signal)


def check_exit(prev_signal, curr_signal, direction):
    return LogisticRegression().check_exit(prev_signal, curr_signal, direction)


# ====================================================================== #
#  Бэктест
# ====================================================================== #
def backtest(df, lookback, n_bars, threshold, sl_points, tp_points, point,
             tick_value, tick_size, retrain_every=100, sim_lot=0.01,
             spread_points=0, commission_per_lot=0):
    """Симуляция сделок на истории с Logistic Regression.

    Параметры
    ---------
    commission_per_lot : float
        Комиссия за полный цикл (вход + выход) в валюте счёта
        на 1 стандартный лот. При ``sim_lot=0.01`` и
        ``commission_per_lot=14`` комиссия за сделку = 0.14.
    sl_points / tp_points : float
        Если 0 — соответствующий стоп не выставляется.
    """
    df = _calc_logreg_cached(df, lookback, n_bars, threshold, retrain_every)

    # Пересчитываем сигналы под текущий threshold
    df = df.copy()
    df['lr_signal'] = 0
    df.loc[df['lr_prob'] >= threshold, 'lr_signal'] = 1
    df.loc[df['lr_prob'] <= (1 - threshold), 'lr_signal'] = -1

    strat = LogisticRegression()

    # 0 → бесконечность: «нет стопа»
    sl_dist = sl_points * point if sl_points > 0 else np.inf
    tp_dist = tp_points * point if tp_points > 0 else np.inf
    spread = spread_points * point
    commission = commission_per_lot * sim_lot

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

        # ── Проверка выхода из открытой позиции ──
        if position:
            exited = False
            p = 0.0
            d = position['direction']

            if d == 'long':
                if current_low <= position['sl']:
                    p = strat.profit_rub(
                        position['entry'], position['sl'],
                        tick_value, tick_size, sim_lot, 'long',
                    )
                    exited = True
                elif current_high >= position['tp']:
                    p = strat.profit_rub(
                        position['entry'], position['tp'],
                        tick_value, tick_size, sim_lot, 'long',
                    )
                    exited = True
                elif strat.check_exit(prev_signal, curr_signal, 'long'):
                    p = strat.profit_rub(
                        position['entry'], curr_close,
                        tick_value, tick_size, sim_lot, 'long',
                    )
                    exited = True
            else:  # short
                if current_high >= position['sl']:
                    p = strat.profit_rub(
                        position['entry'], position['sl'],
                        tick_value, tick_size, sim_lot, 'short',
                    )
                    exited = True
                elif current_low <= position['tp']:
                    p = strat.profit_rub(
                        position['entry'], position['tp'],
                        tick_value, tick_size, sim_lot, 'short',
                    )
                    exited = True
                elif strat.check_exit(prev_signal, curr_signal, 'short'):
                    p = strat.profit_rub(
                        position['entry'], curr_close,
                        tick_value, tick_size, sim_lot, 'short',
                    )
                    exited = True

            if exited:
                p -= (spread / tick_size) * tick_value * sim_lot
                p -= commission
                profit += p
                n_trades += 1
                trade_profits.append(p)
                position = None

        # ── Проверка входа в новую позицию ──
        if position is None:
            entry_dir = strat.check_entry(prev_signal, curr_signal)
            if entry_dir == 'long':
                entry = curr_close + spread
                position = {
                    'direction': 'long',
                    'entry': entry,
                    'sl': entry - sl_dist,
                    'tp': entry + tp_dist,
                }
            elif entry_dir == 'short':
                entry = curr_close - spread
                position = {
                    'direction': 'short',
                    'entry': entry,
                    'sl': entry + sl_dist,
                    'tp': entry - tp_dist,
                }

    return profit, n_trades, trade_profits
