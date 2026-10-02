"""АлисаОк Стратегия Rolling Correlation momentum — вход при высокой корреляции доходности с объёмом."""
import numpy as np
import pandas as pd


def calc_rolling_correlation(df, window=20, corr_threshold=0.5):
    """
    Добавляет колонку 'rolling_corr' с скользящей корреляцией доходности и объёма.

    Корреляция рассчитывается по окну [i-window : i], то есть **не включает** текущий бар i.
    Это исключает data leakage.

    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта корреляции
        corr_threshold: порог корреляции для входа

    Returns:
        DataFrame с колонками 'rolling_corr', 'corr_signal'
    """
    df = df.copy()

    # Процентные изменения цены
    returns = df['close'].pct_change().fillna(0)

    # Векторизованный расчёт скользящей корреляции между returns и volume
    # Используем .rolling(window).corr(), но сдвигаем на 1, чтобы исключить текущий бар
    corr_series = returns.rolling(window - 1).corr(df['volume']).shift(1)

    df['rolling_corr'] = corr_series.fillna(0)

    # Сигнал: высокая положительная корреляция → long, высокая отрицательная → short
    df['corr_signal'] = 0
    df.loc[df['rolling_corr'] > corr_threshold, 'corr_signal'] = 1
    df.loc[df['rolling_corr'] < -corr_threshold, 'corr_signal'] = -1

    return df


def check_entry(prev_signal, curr_signal, position_direction=None):
    """
    Вход при появлении высокой корреляции.

    position_direction: текущее направление позиции ('long'/'short' или None)
    Returns: 'long', 'short' или None
    """
    # Не открываем новую позицию, если уже есть открытая в том же направлении
    if position_direction == 'long' and curr_signal == 1:
        return None
    if position_direction == 'short' and curr_signal == -1:
        return None

    # Long: нет позиции или была short, теперь положительная корреляция
    if curr_signal == 1 and position_direction != 'long':
        return 'long'
    # Short: нет позиции или была long, теперь отрицательная корреляция
    if curr_signal == -1 and position_direction != 'short':
        return 'short'

    return None


def check_exit(prev_signal, curr_signal, direction):
    """
    Выход при падении корреляции к нулю или смене знака.

    Args:
        direction: 'long' или 'short'

    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        # Выходим, если корреляция стала <= 0 (нет импульса) или сменилась на отрицательную
        return curr_signal <= 0
    else:
        # Выходим, если корреляция стала >= 0 (нет импульса) или сменилась на положительную
        return curr_signal >= 0


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, window, corr_threshold, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0,
             commission_per_lot=0):
    """
    Симуляция сделок на истории с Rolling Correlation momentum.

    commission_per_lot: комиссия за полный цикл (вход + выход) на 1 стандартный лот.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_rolling_correlation(df, window, corr_threshold)

    sl_dist = sl_points * point if sl_points > 0 else np.inf
    tp_dist = tp_points * point if tp_points > 0 else np.inf
    spread = spread_points * point
    commission = commission_per_lot * sim_lot

    profit = 0.0
    n_trades = 0
    position = None  # {'direction': 'long'/'short', 'entry': float, 'sl': float, 'tp': float}
    trade_profits = []

    for i in range(1, len(df)):
        prev_signal = df['corr_signal'].iloc[i - 1]
        curr_signal = df['corr_signal'].iloc[i]
        curr_close = df['close'].iloc[i]
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]

        # ── Проверка выхода ──
        if position:
            exited = False
            p = 0.0
            d = position['direction']

            if d == 'long':
                if current_low <= position['sl']:
                    p = _profit(position['entry'], position['sl'],
                                tick_value, tick_size, sim_lot, 'long')
                    exited = True
                elif current_high >= position['tp']:
                    p = _profit(position['entry'], position['tp'],
                                tick_value, tick_size, sim_lot, 'long')
                    exited = True
                elif check_exit(prev_signal, curr_signal, 'long'):
                    p = _profit(position['entry'], curr_close,
                                tick_value, tick_size, sim_lot, 'long')
                    exited = True
            else:  # short
                if current_high >= position['sl']:
                    p = _profit(position['entry'], position['sl'],
                                tick_value, tick_size, sim_lot, 'short')
                    exited = True
                elif current_low <= position['tp']:
                    p = _profit(position['entry'], position['tp'],
                                tick_value, tick_size, sim_lot, 'short')
                    exited = True
                elif check_exit(prev_signal, curr_signal, 'short'):
                    p = _profit(position['entry'], curr_close,
                                tick_value, tick_size, sim_lot, 'short')
                    exited = True

            if exited:
                p -= (spread / tick_size) * tick_value * sim_lot
                p -= commission
                profit += p
                n_trades += 1
                trade_profits.append(p)
                position = None

        # ── Проверка входа (только если нет позиции) ──
        if position is None:
            entry_dir = check_entry(prev_signal, curr_signal, None)
            if entry_dir == 'long':
                entry = curr_close + spread  # покупка по ask
                position = {
                    'direction': 'long',
                    'entry': entry,
                    'sl': entry - sl_dist,
                    'tp': entry + tp_dist,
                }
            elif entry_dir == 'short':
                entry = curr_close - spread  # продажа по bid
                position = {
                    'direction': 'short',
                    'entry': entry,
                    'sl': entry + sl_dist,
                    'tp': entry - tp_dist,
                }

    return profit, n_trades, trade_profits
