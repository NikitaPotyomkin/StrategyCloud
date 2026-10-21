"""Общий движок бэктеста для standalone-стратегий (finding #11).

Единственная реализация цикла «вход по ask/bid → SL/TP → выход со спредом».
Файлы стратегий держат только calc_* и предикаты check_entry/check_exit.

ВНИМАНИЕ: не путать с корневым strategy_engine.py — тот является боевым
движком (ордера, magic, реестр, ранжирование) и тянет MetaTrader5/risk_manager.
Этот модуль лёгкий (только numpy/pandas), чтобы strategies/*.py оставались
терминало-независимыми.
"""
import numpy as np
import pandas as pd


# ═══ Чекпойнт v2: журнал сделок ═══
# Инкремент по новым барам невозможен без списка сделок: из агрегатов (n_trades,
# profit_factor, win_rate) нельзя снять сделку, вышедшую за 30-дневное окно.
# Поэтому движок отдаёт не только профиты, но и время каждой сделки.
#
# TradeList — наследник list. Это принципиально: ВЕСЬ существующий код работает без
# правок (`calc_metrics(trade_profits)`, `len()`, `sum()`, распаковка 3-кортежа),
# а времена сделок едут рядом в атрибуте `times`.
#
# Формат записи сделки: [entry_epoch, exit_epoch, dir(+1 long / -1 short), profit].
# Окно 30 дней отсекается по ВРЕМЕНИ ВЫХОДА: сделка, закрытая внутри окна, остаётся
# (её результат известен), а закрытая раньше — выбывает.
class TradeList(list):
    """Список профитов сделок + времена входа/выхода (атрибут times)."""

    __slots__ = ('times',)

    def __init__(self, *args):
        super().__init__(*args)
        self.times = []


def trade_row(index, i_entry, i_exit, direction, profit):
    """Запись одной сделки для журнала. index — DatetimeIndex баров.

    None, если время бара недоступно: тогда комбинация не станет инкрементальной и
    будет пересчитываться полностью (безопасный дефолт).
    """
    try:
        t_in = int(index[i_entry].timestamp())
        t_out = int(index[i_exit].timestamp())
    except (AttributeError, TypeError, ValueError, IndexError):
        return None
    return [t_in, t_out, 1 if direction == 'long' else -1, round(float(profit), 2)]


def atr(df, period=14):
    """ATR по Уайлдеру (EMA-сглаживание). На прогреве возвращает NaN (не 0)."""
    high, low, close = df['high'], df['low'], df['close']
    prev_close = close.shift(1)
    tr = pd.concat([high - low,
                    (high - prev_close).abs(),
                    (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


def trade_profit(entry, exit_price, tick_value, tick_size, lot, direction):
    """P&L одной сделки в валюте счёта (бывший per-file _profit)."""
    diff = (exit_price - entry) if direction == 'long' else (entry - exit_price)
    return (diff / tick_size) * tick_value * lot


def state_entry(prev_s, curr_s):
    """Вход по состоянию 'k' ∈ {-1,0,1}: переход в +1 (long) / -1 (short)."""
    if curr_s == 1 and prev_s != 1:
        return 'long'
    if curr_s == -1 and prev_s != -1:
        return 'short'
    return None


def state_exit(prev_s, curr_s, direction):
    """Выход по состоянию: состояние больше не совпадает с текущей позицией."""
    if direction == 'long':
        return curr_s != 1
    return curr_s != -1


def run_backtest(df, calc_fn, check_entry, check_exit, param_key,
                 sl_points, tp_points, point, tick_value, tick_size,
                 sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits).

    calc_fn(df, param_key) обязан положить сигнал в колонку 'k'.
    Модель спреда: вход по ask/bid (close ± spread), и на каждом выходе
    результат уменьшается на один спред (round-trip: ask-вход, bid-выход).
    """
    df = calc_fn(df, param_key)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = TradeList()

    for i in range(1, len(df)):
        prev_k = df['k'].iloc[i - 1]
        curr_k = df['k'].iloc[i]
        high = df['high'].iloc[i]
        low = df['low'].iloc[i]
        close = df['close'].iloc[i]

        if position:
            exited = False
            p = 0.0
            d = position['direction']
            if d == 'long':
                if low <= position['sl']:
                    p = trade_profit(position['entry'], position['sl'], tick_value, tick_size, sim_lot, 'long')
                    p -= (spread / tick_size) * tick_value * sim_lot
                    exited = True
                elif high >= position['tp']:
                    p = trade_profit(position['entry'], position['tp'], tick_value, tick_size, sim_lot, 'long')
                    p -= (spread / tick_size) * tick_value * sim_lot
                    exited = True
                elif check_exit(prev_k, curr_k, 'long'):
                    p = trade_profit(position['entry'], close, tick_value, tick_size, sim_lot, 'long')
                    p -= (spread / tick_size) * tick_value * sim_lot
                    exited = True
            else:
                if high >= position['sl']:
                    p = trade_profit(position['entry'], position['sl'], tick_value, tick_size, sim_lot, 'short')
                    p -= (spread / tick_size) * tick_value * sim_lot
                    exited = True
                elif low <= position['tp']:
                    p = trade_profit(position['entry'], position['tp'], tick_value, tick_size, sim_lot, 'short')
                    p -= (spread / tick_size) * tick_value * sim_lot
                    exited = True
                elif check_exit(prev_k, curr_k, 'short'):
                    p = trade_profit(position['entry'], close, tick_value, tick_size, sim_lot, 'short')
                    p -= (spread / tick_size) * tick_value * sim_lot
                    exited = True

            if exited:
                profit += p
                n_trades += 1
                trade_profits.append(p)
                _row = trade_row(df.index, _entry_i, i, d, p)
                if _row is not None:
                    trade_profits.times.append(_row)
                position = None

        if position is None:
            entry_dir = check_entry(prev_k, curr_k)
            if entry_dir == 'long':
                entry = close + spread
                _entry_i = i
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short':
                entry = close - spread
                _entry_i = i
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
