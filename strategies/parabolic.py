import numpy as np
import pandas as pd


# Стандартные параметры Parabolic SAR
SAR_STEP = 0.02
SAR_MAX = 0.2


def calc_parabolic(df, step=SAR_STEP, max_val=SAR_MAX):
    """
    Вычисляет Parabolic SAR и добавляет колонку 'sar' в копию DataFrame.
    Использует стандартный алгоритм Parabolic SAR с клиппингом.
    """
    high = df['high'].values
    low = df['low'].values
    n = len(df)

    sar = np.full(n, np.nan)
    ep = np.full(n, np.nan)   # extreme point
    af = np.full(n, np.nan)   # acceleration factor

    # Инициализация
    sar[0] = low[0]
    ep[0] = high[0]
    af[0] = step
    trend = 1  # 1 = long, -1 = short

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
                continue

            # Обновление EP и AF
            if low[i] < ep_prev:
                ep[i] = low[i]
                af[i] = min(af_prev + step, max_val)
            else:
                ep[i] = ep_prev
                af[i] = af_prev

    df = df.copy()
    df['sar'] = sar
    return df


def check_entry(prev_sar, current_sar, prev_price, current_price):
    """
    Вход по пересечению цены через SAR.
    """
    # Цена была выше SAR, стала ниже → тренд сменился вниз → short
    if prev_price > prev_sar and current_price < current_sar:
        return 'short'
    # Цена была ниже SAR, стала выше → тренд сменился вверх → long
    if prev_price < prev_sar and current_price > current_sar:
        return 'long'
    return None


def check_exit(prev_sar, current_sar, prev_price, current_price, direction):
    """
    Выход при пересечении цены через SAR в обратную сторону.
    """
    if direction == 'long':
        # Цена была выше SAR, стала ниже → выход из long
        return prev_price > prev_sar and current_price < current_sar
    else:
        # Цена была ниже SAR, стала выше → выход из short
        return prev_price < prev_sar and current_price > current_sar


def _profit(entry, exit_price, tick_value, tick_size, lot, direction):
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def backtest(df, step, max_val, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0):
    """
    Симуляция сделок на истории с учётом Parabolic SAR.
    Возвращает (profit, n_trades, trade_profits).
    """
    df = calc_parabolic(df, step, max_val)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = []

    for i in range(2, len(df)):
        prev_sar = df['sar'].iloc[i - 1]
        current_sar = df['sar'].iloc[i]
        prev_close = df['close'].iloc[i - 1]
        current_close = df['close'].iloc[i]
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
                elif check_exit(prev_sar, current_sar, prev_close, current_close, 'long'):
                    p = _profit(position['entry'], current_close,
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
                elif check_exit(prev_sar, current_sar, prev_close, current_close, 'short'):
                    p = _profit(position['entry'], current_close,
                                tick_value, tick_size, sim_lot, 'short')
                    exited = True

            if exited:
                # Спред вычитается один раз для обоих направлений
                p -= (spread / tick_size) * tick_value * sim_lot
                profit += p
                n_trades += 1
                trade_profits.append(p)
                position = None

        # ── Проверка входа ──
        if position is None:
            entry_dir = check_entry(prev_sar, current_sar, prev_close, current_close)
            if entry_dir == 'long':
                entry = current_close
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = current_close
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
