"""Общий движок бэктеста для standalone-стратегий (finding #11).

Единственная реализация цикла «вход по ask/bid → SL/TP → выход со спредом».
Файлы стратегий держат только calc_* и предикаты check_entry/check_exit.

ВНИМАНИЕ: не путать с корневым strategy_engine.py — тот является боевым
движком (ордера, magic, реестр, ранжирование) и тянет MetaTrader5/risk_manager.
Этот модуль лёгкий (только numpy/pandas), чтобы strategies/*.py оставались
терминало-независимыми.

ДВЕ РЕАЛИЗАЦИИ ЦИКЛА (замер 22.10.2026)
    Петля была 107.5 мин из 203 на корзину — не из-за `for`, а из-за чтения
    df['col'].iloc[i]: это Python-цепочка DataFrame.__getitem__ →
    Series._iLocIndexer.__getitem__ → _ixs → создание объекта на КАЖДОЕ
    значение (~7-10 мкс против ~50 нс у numpy). 5 чтений на бар × 719 бар ×
    60 543 комбо ≈ 43.6 млн итераций.
    Поэтому колонки конвертируются в numpy-массивы ОДИН раз до цикла, а
    математика и порядок операций сохранены байт-в-байт (паритет 1e-6).

    Переключатель: config.BacktestConfig.numpy_loop (или переменная окружения
    STRATEGYCLOUD_NUMPY_LOOP=0). False возвращает прежний iloc-цикл — откат
    одной строкой в config.py без правки кода. Гейт: tools/loop_parity.py.
"""
import os

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


# ═══ Переключатель реализации цикла ═══
# None = решение ещё не принято (ленивое чтение config/env на первом вызове).
NUMPY_LOOP = None


def _resolve_numpy_loop(cfg=None):
    """True/False: аргумент → переменная окружения → config → True."""
    if cfg is not None:
        return bool(getattr(cfg, 'numpy_loop', True))
    env = os.environ.get('STRATEGYCLOUD_NUMPY_LOOP')
    if env is not None:
        return env.strip() not in ('0', 'false', 'False', 'no', 'off', '')
    try:
        from config import build_default_configs
        return bool(getattr(build_default_configs().backtest_config, 'numpy_loop', True))
    except Exception:
        return True


def set_numpy_loop(flag):
    """Переключить реализацию без правки config (нужно паритету и замерам)."""
    global NUMPY_LOOP
    NUMPY_LOOP = bool(flag)
    return NUMPY_LOOP


def numpy_loop_enabled():
    """Текущее значение флага (ленивая инициализация из config/env)."""
    global NUMPY_LOOP
    if NUMPY_LOOP is None:
        NUMPY_LOOP = _resolve_numpy_loop()
    return bool(NUMPY_LOOP)


def _open_array(df):
    """Open-цены как numpy-массив длиной n+1 (последний элемент — NaN).

    NaN-сентинел означает «следующего бара нет»: сигнал последнего бара
    исполнять не по чему, и вход там пропускается (проверка np.isfinite в
    петле). Если колонки open нет — фолбэк на close (прежняя модель входа).
    """
    col = df['open'] if 'open' in df.columns else df['close']
    return np.append(col.to_numpy(dtype=float), np.nan)


def run_backtest(df, calc_fn, check_entry, check_exit, param_key,
                 sl_points, tp_points, point, tick_value, tick_size,
                 sim_lot=0.01, spread_points=0):
    """Симуляция на H1 с учётом спреда. Возвращает (profit, n_trades, trade_profits).

    calc_fn(df, param_key) обязан положить сигнал в колонку 'k'.
    check_entry(prev, curr) обязан вернуть 'long' / 'short' / None — как
    state_entry ниже; булев контракт файлов (True/False) здесь не работает.
    Модель спреда: вход по ask/bid (open следующего бара ± spread), а на
    выходе результат уменьшается на один спред (ask-вход, bid-выход).
    Модель входа (30.10.2026): сигнал бара i исполняется по open бара i+1.
    Прежний вход по close[i] того же бара давал систематический оптимизм —
    цена закрытия сигнального бара уже известна в момент «входа».
    """
    df = calc_fn(df, param_key)
    sl_dist = sl_points * point
    tp_dist = tp_points * point
    spread = spread_points * point
    if numpy_loop_enabled():
        return _simulate_arrays(df, check_entry, check_exit, sl_dist, tp_dist,
                                spread, tick_value, tick_size, sim_lot)
    return _simulate_iloc(df, check_entry, check_exit, sl_dist, tp_dist,
                          spread, tick_value, tick_size, sim_lot)


def _simulate_arrays(df, check_entry, check_exit, sl_dist, tp_dist, spread,
                     tick_value, tick_size, sim_lot):
    """Быстрая петля: колонки читаются из numpy-массивов (~50 нс вместо ~7-10 мкс).

    Логика, порядок проверок, арифметика и запись журнала — те же, что в
    _simulate_iloc. Это условие паритета по профитам сделок (1e-6).
    """
    k_arr = df['k'].to_numpy()
    open_arr = _open_array(df)
    high_arr = df['high'].to_numpy(dtype=float)
    low_arr = df['low'].to_numpy(dtype=float)
    close_arr = df['close'].to_numpy(dtype=float)
    index = df.index
    n = len(df)

    # Локальные ссылки: поиск в globals на каждой сделке дороже самого расчёта.
    _profit = trade_profit
    _row = trade_row
    _entry_fn = check_entry
    _exit_fn = check_exit

    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = TradeList()

    for i in range(1, n):
        prev_k = k_arr[i - 1]
        curr_k = k_arr[i]
        high = high_arr[i]
        low = low_arr[i]
        close = close_arr[i]

        if position is not None:
            d = position['direction']
            entry = position['entry']
            exit_price = None
            if d == 'long':
                if low <= position['sl']:
                    exit_price = position['sl']
                elif high >= position['tp']:
                    exit_price = position['tp']
                elif _exit_fn(prev_k, curr_k, 'long'):
                    exit_price = close
            else:
                if high >= position['sl']:
                    exit_price = position['sl']
                elif low <= position['tp']:
                    exit_price = position['tp']
                elif _exit_fn(prev_k, curr_k, 'short'):
                    exit_price = close

            if exit_price is not None:
                p = _profit(entry, exit_price, tick_value, tick_size, sim_lot, d)
                p -= (spread / tick_size) * tick_value * sim_lot
                profit += p
                n_trades += 1
                trade_profits.append(p)
                _rec = _row(index, _entry_i, i, d, p)
                if _rec is not None:
                    trade_profits.times.append(_rec)
                position = None

        if position is None:
            entry_dir = _entry_fn(prev_k, curr_k)
            if entry_dir == 'long' and np.isfinite(open_arr[i + 1]):
                entry = open_arr[i + 1] + spread
                _entry_i = i + 1      # сделка принадлежит бару входа, а не сигнала
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short' and np.isfinite(open_arr[i + 1]):
                entry = open_arr[i + 1] - spread
                _entry_i = i + 1      # сделка принадлежит бару входа, а не сигнала
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits


def _simulate_iloc(df, check_entry, check_exit, sl_dist, tp_dist, spread,
                   tick_value, tick_size, sim_lot):
    """Прежняя петля (эталон паритета и откат при numpy_loop=False).

    Читает df['col'].iloc[i] — медленно, но это исходное поведение движка
    с 2023 года, по нему валидировались все исторические прогоны.
    """
    profit = 0.0
    n_trades = 0
    position = None
    trade_profits = TradeList()

    open_arr = _open_array(df)

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
            if entry_dir == 'long' and np.isfinite(open_arr[i + 1]):
                entry = open_arr[i + 1] + spread
                _entry_i = i + 1      # сделка принадлежит бару входа, а не сигнала
                position = {'direction': 'long', 'entry': entry,
                            'sl': entry - sl_dist, 'tp': entry + tp_dist}
            elif entry_dir == 'short' and np.isfinite(open_arr[i + 1]):
                entry = open_arr[i + 1] - spread
                _entry_i = i + 1      # сделка принадлежит бару входа, а не сигнала
                position = {'direction': 'short', 'entry': entry,
                            'sl': entry + sl_dist, 'tp': entry - tp_dist}

    return profit, n_trades, trade_profits
