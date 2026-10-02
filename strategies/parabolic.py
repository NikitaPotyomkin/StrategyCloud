"""АлисаОК Стратегия Parabolic SAR — вход при пересечении цены через SAR."""
import numpy as np
import pandas as pd


# Стандартные параметры Parabolic SAR
SAR_STEP = 0.02
SAR_MAX = 0.2


def calc_parabolic(df, step=SAR_STEP, max_val=SAR_MAX):
    """
    Вычисляет Parabolic SAR.

    Добавляет колонки:
      'sar'       — значение SAR для каждого бара;
      'sar_trend'  — направление тренда (1 = вверх, -1 = вниз).
    """
    high = df['high'].values
    low = df['low'].values
    n = len(df)

    sar = np.full(n, np.nan)
    ep = np.full(n, np.nan)
    af = np.full(n, np.nan)
    trend_arr = np.full(n, np.nan)

    if n == 0:
        df = df.copy()
        df['sar'] = sar
        df['sar_trend'] = trend_arr
        return df

    # Инициализация
    sar[0] = low[0]
    ep[0] = high[0]
    af[0] = step
    trend = 1
    trend_arr[0] = trend

    for i in range(1, n):
        sar_prev = sar[i - 1]
        ep_prev = ep[i - 1]
        af_prev = af[i - 1]

        if trend == 1:
            sar[i] = sar_prev + af_prev * (ep_prev - sar_prev)
            # Клиппинг: SAR не выше low двух предыдущих баров
            if i >= 2:
                sar[i] = min(sar[i], low[i - 1], low[i - 2])
            else:
                sar[i] = min(sar[i], low[i - 1])

            # Разворот: текущий low пробил SAR
            if low[i] <= sar[i]:
                trend = -1
                sar[i] = ep_prev
                ep[i] = low[i]
                af[i] = step
                trend_arr[i] = trend
                continue

            # Обновление EP и AF
            if high[i] > ep_prev:
                ep[i] = high[i]
                af[i] = min(af_prev + step, max_val)
            else:
                ep[i] = ep_prev
                af[i] = af_prev

        else:
            sar[i] = sar_prev + af_prev * (ep_prev - sar_prev)
            # Клиппинг: SAR не ниже high двух предыдущих баров
            if i >= 2:
                sar[i] = max(sar[i], high[i - 1], high[i - 2])
            else:
                sar[i] = max(sar[i], high[i - 1])

            # Разворот: текущий high пробил SAR
            if high[i] >= sar[i]:
                trend = 1
                sar[i] = ep_prev
                ep[i] = high[i]
                af[i] = step
                trend_arr[i] = trend
                continue

            # Обновление EP и AF
            if low[i] < ep_prev:
                ep[i] = low[i]
                af[i] = min(af_prev + step, max_val)
            else:
                ep[i] = ep_prev
                af[i] = af_prev

        trend_arr[i] = trend

    df = df.copy()
    df['sar'] = sar
    df['sar_trend'] = trend_arr
    return df


def check_entry(prev_trend, curr_trend):
    """
    Вход по смене направления тренда SAR.

    Использует направление тренда из calc_parabolic (sar_trend),
    а не close-пересечение — это точнее, так как SAR переворачивается
    по high/low, а не по close.
    """
    if prev_trend == 1 and curr_trend == -1:
        return 'short'
    if prev_trend == -1 and curr_trend == 1:
        return 'long'
    return None


def check_exit(prev_trend, curr_trend, direction):
    """
    Выход при смене направления тренда SAR.
    """
    if direction == 'long':
        return curr_trend == -1
    else:
        return curr_trend == 1


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, step, max_val, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0, commission_per_lot=0):
    """
    Симуляция сделок на истории с Parabolic SAR.

    Параметры
    ---------
    commission_per_lot : float
        Комиссия за полный цикл (вход + выход) на 1 стандартный лот.
    sl_points / tp_points : float
        Если 0 — соответствующий стоп не выставляется.
    """
    df = calc_parabolic(df, step, max_val)

    # 0 → бесконечность: «нет стопа»
    sl_dist = sl_points * point if sl_points > 0 else np.inf
    tp_dist = tp_points * point if tp_points > 0 else np.inf
    spread = spread_points * point
    commission = commission_per_lot * sim_lot

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(2, len(df)):
        prev_trend = df['sar_trend'].iloc[i - 1]
        curr_trend = df['sar_trend'].iloc[i]
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
                elif check_exit(prev_trend, curr_trend, 'long'):
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
                elif check_exit(prev_trend, curr_trend, 'short'):
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

        # ── Проверка входа ──
        if position is None:
            entry_dir = check_entry(prev_trend, curr_trend)
            if entry_dir == 'long':
                entry = curr_close + spread
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = curr_close - spread
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
