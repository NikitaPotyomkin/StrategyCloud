"""Стратегия Rolling Sharpe filter — вход при Sharpe(N) > 0.5, выход при Sharpe < 0."""
import numpy as np
import pandas as pd


def calc_rolling_sharpe(df, window, sharpe_entry=0.5, sharpe_exit=0.0):
    """
    Добавляет колонку 'sharpe' с скользящим коэффициентом Шарпа.

    Args:
        df: DataFrame с OHLCV
        window: размер окна для расчёта
        sharpe_entry: порог Sharpe для входа
        sharpe_exit: порог Sharpe для выхода

    Returns:
        DataFrame с колонкой 'sharpe'
    """
    df = df.copy()
    returns = df['close'].pct_change().fillna(0)

    # ── Sharpe (векторно, без цикла по барам) ──
    # Sharpe[i] = mean / std * sqrt(252*24), окно returns[i-window:i] (БЕЗ текущего бара),
    # std — выборочное (ddof=1). Поэтому rolling(...).shift(1): сдвигаем окно на бар назад.
    # Для i < window и при std == 0 → 0.
    n = len(df)
    sharpe_values = np.zeros(n, dtype=float)

    if window > 0 and n > window:
        mean_arr = returns.rolling(window).mean().shift(1).to_numpy()
        std_arr = returns.rolling(window).std().shift(1).to_numpy()   # ddof=1
        with np.errstate(divide='ignore', invalid='ignore'):
            sharpe = mean_arr / std_arr * np.sqrt(252 * 24)   # Annualized
        good = std_arr != 0
        sharpe_values[window:] = np.where(good[window:], sharpe[window:], 0.0)

    df['sharpe'] = sharpe_values
    return df


def check_entry(prev_sharpe, curr_sharpe, sharpe_entry):
    """
    Вход при появлении сильного Sharpe (тренд с доходностью).

    Returns:
        'long' (Sharpe > 0.5 → восходящий), 'short' (Sharpe < -0.5 → нисходящий) или None
    """
    # Long: был в нейтральной зоне, теперь Sharpe > sharpe_entry
    if prev_sharpe <= sharpe_entry and curr_sharpe > sharpe_entry:
        return 'long'
    # Short: был в нейтральной зоне, теперь Sharpe < -sharpe_entry
    if prev_sharpe >= -sharpe_entry and curr_sharpe < -sharpe_entry:
        return 'short'
    return None


def check_exit(prev_sharpe, curr_sharpe, sharpe_exit, direction):
    """
    Выход при возврате Sharpe к нулю.

    Args:
        direction: 'long' или 'short'

    Returns:
        True если нужно выйти
    """
    if direction == 'long':
        return curr_sharpe <= sharpe_exit
    else:
        return curr_sharpe >= sharpe_exit


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, window, sharpe_entry, sharpe_exit, sl_points, tp_points, point,
             tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с Rolling Sharpe filter.

    Returns:
        (profit, n_trades, trade_profits)
    """
    df = calc_rolling_sharpe(df, window, sharpe_entry, sharpe_exit)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    from strategies._bt_core import TradeList, trade_row  # v2: журнал сделок
    trade_profits = TradeList()

    _c_sharpe = df['sharpe'].to_numpy()   # numpy-петля: позиционный доступ
    _c_close = df['close'].to_numpy()   # numpy-петля: позиционный доступ
    _c_high = df['high'].to_numpy()   # numpy-петля: позиционный доступ
    _c_low = df['low'].to_numpy()   # numpy-петля: позиционный доступ
    for i in range(1, len(df)):
        prev_sharpe = _c_sharpe[i - 1]
        curr_sharpe = _c_sharpe[i]
        curr_close = _c_close[i]
        current_high = _c_high[i]
        current_low = _c_low[i]

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
                elif check_exit(prev_sharpe, curr_sharpe, sharpe_exit, 'long'):
                    p = _profit(position['entry'], curr_close,
                                tick_value, tick_size, sim_lot, 'long')
                    exited = True
            else:
                if current_high >= position['sl']:
                    p = _profit(position['entry'], position['sl'],
                                tick_value, tick_size, sim_lot, 'short')
                    exited = True
                elif current_low <= position['tp']:
                    p = _profit(position['entry'], position['tp'],
                                tick_value, tick_size, sim_lot, 'short')
                    exited = True
                elif check_exit(prev_sharpe, curr_sharpe, sharpe_exit, 'short'):
                    p = _profit(position['entry'], curr_close,
                                tick_value, tick_size, sim_lot, 'short')
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
            entry_dir = check_entry(prev_sharpe, curr_sharpe, sharpe_entry)
            if entry_dir == 'long':
                entry = curr_close - spread
                _entry_i = i
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close + spread
                _entry_i = i
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
