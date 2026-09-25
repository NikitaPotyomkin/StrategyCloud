"""Утилиты, MT5-операции и бэктест."""
import MetaTrader5 as mt5
import time
import datetime
import pandas as pd
import numpy as np
import json
import glob
import os
import csv
import hashlib
from itertools import product


# ═══ ЧЕКПОЙНТЫ БЭКТЕСТА ═══
def _checkpoint_dir():
    """Путь к папке чекпойнтов."""
    base = os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, 'checkpoints')
    os.makedirs(d, exist_ok=True)
    return d


def _checkpoint_file(symbol):
    """Путь к файлу чекпойнта для символа."""
    return os.path.join(_checkpoint_dir(), f"{symbol}.json")


def load_checkpoint(symbol):
    """Загрузить результаты для символа из чекпойнта. Возвращает список результатов или None."""
    path = _checkpoint_file(symbol)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('results', [])
    except (json.JSONDecodeError, KeyError):
        return None


def save_checkpoint(symbol, results, data_hash=None):
    """Сохранить результаты для символа в чекпойнт."""
    path = _checkpoint_file(symbol)
    data = {
        'symbol': symbol,
        'timestamp': datetime.datetime.now().isoformat(),
        'n_results': len(results),
        'data_hash': data_hash,
        'results': results
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))


def remove_checkpoint(symbol):
    """Удалить чекпойнт после успешного завершения."""
    path = _checkpoint_file(symbol)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def list_checkpoints():
    """Вернуть список символов с готовыми чекпойнтами."""
    d = _checkpoint_dir()
    if not os.path.exists(d):
        return []
    checkpoints = []
    for fname in os.listdir(d):
        if fname.endswith('.json'):
            symbol = fname[:-5]  # убрать .json
            checkpoints.append(symbol)
    return sorted(checkpoints)


# ═══ BACKTEST-ФУНКЦИИ ДЛЯ МУЛЬТИПРОЦЕССИНГА ═══
# Эти функции перенесены сюда, чтобы multiprocessing мог их сериализовать
def _backtest_stoch(df, k_period, sl_points, tp_points, point, tick_value, tick_size, spread_points=0):
    """Backtest для Stochastic."""
    from strategies.stochastic import backtest as stoch_backtest
    return stoch_backtest(df, k_period, sl_points, tp_points, point, tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_parabolic(df, step, max_val, sl_points, tp_points, point, tick_value, tick_size, spread_points=0):
    """Backtest для Parabolic SAR."""
    from strategies.parabolic import backtest as parab_backtest
    return parab_backtest(df, step, max_val, sl_points, tp_points, point, tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_ma(df, period, sl_points, tp_points, point, tick_value, tick_size, spread_points=0):
    """Backtest для Moving Average."""
    from strategies.moving_average import backtest as ma_backtest
    return ma_backtest(df, period, sl_points, tp_points, point, tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_rf(df, lookback, n_bars, threshold, sl_points, tp_points, point, tick_value, tick_size, spread_points=0, sim_lot=0.01):
    """Backtest для Random Forest."""
    from strategies.random_forest import backtest as rf_backtest
    return rf_backtest(df, lookback, n_bars, threshold, sl_points, tp_points, point, tick_value, tick_size, sim_lot=sim_lot, spread_points=spread_points)


def _backtest_logreg(df, lookback, n_bars, threshold, sl_points, tp_points, point, tick_value, tick_size, spread_points=0, sim_lot=0.01):
    """Backtest для Logistic Regression."""
    from strategies.logreg import backtest as logreg_backtest
    return logreg_backtest(df, lookback, n_bars, threshold, sl_points, tp_points, point, tick_value, tick_size, sim_lot=sim_lot, spread_points=spread_points)


def _backtest_macd_rsi(df, macd_fast, macd_slow, macd_signal, rsi_period,
                       rsi_oversold, rsi_overbought, sl_points, tp_points,
                       point, tick_value, tick_size, spread_points=0):
    """Backtest для MACD + RSI."""
    from strategies.macd_rsi import backtest_macd_rsi
    return backtest_macd_rsi(df, macd_fast, macd_slow, macd_signal, rsi_period,
                             rsi_oversold, rsi_overbought, sl_points, tp_points,
                             point, tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_bollinger(df, bb_period, bb_std, volume_period,
                        sl_points, tp_points, point, tick_value, tick_size, spread_points=0):
    """Backtest для Bollinger Breakout."""
    from strategies.bollinger_breakout import backtest_bollinger
    return backtest_bollinger(df, bb_period, bb_std, volume_period,
                              sl_points, tp_points, point, tick_value, tick_size,
                              sim_lot=0.01, spread_points=spread_points)


def _backtest_ema_crossover(df, ema_fast, ema_slow, sl_points, tp_points,
                            point, tick_value, tick_size, spread_points=0):
    """Backtest для EMA Crossover."""
    from strategies.ema_crossover import backtest_ema_crossover
    return backtest_ema_crossover(df, ema_fast, ema_slow, sl_points, tp_points,
                                  point, tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_rsi_divergence(df, rsi_period, lookback, threshold,
                             sl_points, tp_points, point, tick_value, tick_size,
                             spread_points=0):
    """Backtest для RSI Divergence."""
    from strategies.rsi_divergence import backtest_rsi_divergence
    return backtest_rsi_divergence(df, rsi_period, lookback, threshold,
                                   sl_points, tp_points, point, tick_value, tick_size,
                                   sim_lot=0.01, spread_points=spread_points)


def _backtest_ichimoku(df, tenkan, kijun, senkou_b, displacement,
                       sl_points, tp_points, point, tick_value, tick_size,
                       spread_points=0):
    """Backtest для Ichimoku Cloud."""
    from strategies.ichimoku_cloud import backtest_ichimoku
    return backtest_ichimoku(df, tenkan, kijun, senkou_b, displacement,
                             sl_points, tp_points, point, tick_value, tick_size,
                             sim_lot=0.01, spread_points=spread_points)


# ═══ УТИЛИТЫ ВРЕМЕНИ И ДАТЫ ═══
def curr_time():
    """Текущее время в формате ЧЧ:ММ."""
    now = datetime.datetime.now()
    return now.strftime("%H:%M")


def get_weekday():
    """Получить день недели (0=понедельник, 6=воскресенье)."""
    return datetime.datetime.today().weekday()


def get_time_item(item_num):
    """Получает элементы сегодняшней даты поэлементно (год, месяц, дни, часы, минуты)."""
    year, month, day, hour, min_ = map(int, time.strftime("%Y %m %d %H %M").split())
    items = [year, month, day, hour, min_]
    return items[item_num]


# ═══ УТИЛИТЫ ФАЙЛОВ И ЛОГОВ ═══
def get_last_file(path):
    """Получить последний файл по glob-паттерну."""
    list_of_files = glob.glob(path)
    if not list_of_files:
        return None
    return max(list_of_files, key=os.path.getctime)


def write_to_log_file(text):
    """Записать сообщения в лог-файл."""
    with open('analytics\\log_file.txt', 'w') as f:
        if isinstance(text, str):
            f.write(text + '\n')
        elif isinstance(text, list):
            for x in text:
                f.write(x + '\n')


# ═══ ПОДКЛЮЧЕНИЕ К MT5 ═══
def terminal_on(acc):
    """Подключиться к терминалу MetaTrader 5."""
    print(f"Подключаемся к аккаунту: {acc}")
    i, limit, interval = 0, 5, 150
    accounts_credentials = {
        'demo': [2000066590, "3cm%3dxbZx", "AlfaForexRU-Real"]
    }
    while i < limit:
        try:
            creds = accounts_credentials[acc]
            print(f'Попытка подключения: {creds}')
        except KeyError:
            print('Указанный счет не найден!')
            return
        login, password, server = creds[0], creds[1], creds[2]
        if not mt5.initialize(login=login, server=server, password=password):
            print("initialize() failed, error code =", mt5.last_error())
            i += 1
            msg = f'{curr_time()} попытка подключения {i}'
            print(msg)
            time.sleep(interval * 2)
            if i == limit - 1:
                quit()
        else:
            print(f"Подключение к счету {accounts_credentials[acc][0]}: успешно")
            break


def get_equity():
    """Получить данные о текущем портфеле."""
    account_info = mt5.account_info()
    if account_info is not None:
        account_info_dict = mt5.account_info()._asdict()
        df = pd.DataFrame(list(account_info_dict.items()), columns=['property', 'value'])
        balance = df["value"].iloc[10]
        msg = f'баланс: {balance}'
    else:
        msg = 'Нет данных о счете!'
    return msg


# ═══ ТОРГОВЫЕ ОПЕРАЦИИ (СТАРЫЕ) ═══
def determine_parameters(order_open_pos, symbol):
    """Определить параметры для закрытия ордера."""
    if order_open_pos == mt5.ORDER_TYPE_BUY:
        close_price = mt5.symbol_info_tick(symbol).ask
        order_close_pos = mt5.ORDER_TYPE_SELL
    else:
        close_price = mt5.symbol_info_tick(symbol).bid
        order_close_pos = mt5.ORDER_TYPE_BUY

    if order_open_pos == mt5.ORDER_TYPE_BUY:
        price = mt5.symbol_info_tick(symbol).bid
    else:
        price = mt5.symbol_info_tick(symbol).ask

    return close_price, order_close_pos, price


def send_order(lot, order_open_pos, symbol, price, basis):
    """Формирует ордер на открытие (старая версия)."""
    now = datetime.datetime.now().strftime('%H:%M')
    print(f'{now} открытие ордера {symbol}, {lot} lot')
    deviation = 12
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_open_pos,
        "price": price,
        "deviation": deviation,
        "magic": 234000,
        "comment": basis,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    i = 0
    while i < 1:
        result = mt5.order_send(request)
        time.sleep(1)
        i += 1
    return result


def close_order(lot, type_, symbol, close_price, ticket):
    """Формирует ордер на закрытие (старая версия)."""
    if type_ == 'mt5.ORDER_TYPE_SELL':
        type_ = mt5.ORDER_TYPE_SELL
    elif type_ == 'mt5.ORDER_TYPE_BUY':
        type_ = mt5.ORDER_TYPE_BUY
    lot = float(lot)
    msg = f'закрытие позиции: {symbol} {str(lot)} лот'
    send_telegram(msg, True)
    price = close_price
    deviation = 15
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": type_,
        "price": price,
        "deviation": deviation,
        "magic": 234000,
        "position": ticket,
        "comment": "closing",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK
    }
    i, result = 0, None
    while result is None or 'No prices' in str(result):
        result = mt5.order_send(request)
        time.sleep(1)
        i += 1
        if i == 10:
            print(f'{curr_time()}: не получается закрыть тикет {ticket}. Проверьте кнопку разрешения торговли в терминале!')
            break
    return result


def create_order(symbol, order_type, lot, basis, adv_id, spread):
    """Инициирует создание ордера на сделку (старая версия)."""
    if order_type == mt5.ORDER_TYPE_SELL:
        msg = f'{curr_time()} {symbol} перекуплен в зоне {basis}, продаем (спред {spread})'
        send_telegram(msg, True)
    if order_type == mt5.ORDER_TYPE_BUY:
        msg = f'{curr_time()} {symbol} перепродан в зоне {basis}, покупаем (спред {spread})'
        send_telegram(msg, True)
    order_open_pos = order_type
    values = determine_parameters(order_open_pos, symbol)
    result = send_order(lot, order_open_pos, symbol, values[2], 'p' + str(adv_id) + " " + basis)
    if result is None:
        print('      ошибка открытия ордера')
    else:
        print('      ticket: ' + str(result.order))


# ═══ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ═══
def check_close_status(type_, symbol, op, pct_50, curr_price, volume, ticket):
    """Проверить статус закрытия позиции."""
    action, h = '', get_time_item(3)
    if 'JPY' in symbol:
        delta = 0.015
    else:
        delta = 0.00015

    if h < 23:
        op, pct_50 = op[symbol], pct_50[symbol]['p50']
        if type_ == 0:
            target_finres = round(op - pct_50, 5) - delta
            if curr_price > target_finres:
                action = f"{str(ticket)} {symbol} SELL {volume} BY MARKET"
            else:
                action = "HOLD"
        elif type_ == 1:
            target_finres = round(op + pct_50, 5) + delta
            if curr_price < target_finres:
                action = f"{str(ticket)} {symbol} BUY {volume} BY MARKET"
            else:
                action = "HOLD"
    else:
        if type_ == 0:
            action = f"{str(ticket)} {symbol} SELL {volume} BY MARKET"
        elif type_ == 1:
            action = f"{str(ticket)} {symbol} BUY {volume} BY MARKET"
    return action


def check_spread(symbol, bid, ask, spread_lims):
    """Проверить размер спреда."""
    spread_x = 1000
    if 'JPY' in symbol:
        spread_x, round_x = 1000, 3
    else:
        spread_x, round_x = spread_x * 100, 5
    spread = int(round(float(ask) - float(bid), round_x) * spread_x)
    lim = spread_lims[symbol]
    flag = spread <= lim
    return flag, spread


def split_volume(lot):
    """Разделить объём на части."""
    t = get_time_item(3)
    part_lot = round((float(lot) / (24 - int(t))), 2)
    return part_lot


def calc_lot(equity_percentage):
    """Рассчитать лот на основе процента от капитала."""
    account_info_dict = mt5.account_info()._asdict()
    df = pd.DataFrame(list(account_info_dict.items()), columns=['property', 'value'])
    balance = df["value"].iloc[10]
    lot = round((balance * equity_percentage / 100) / 1000, 2)
    return lot


def calc_close_delta(value, symbol):
    """Рассчитать дельту для закрытия."""
    if symbol == 'USDJPYrfd':
        delta = value / 1000
    else:
        delta = value / 100000
    return delta


def find_lot_size():
    """Загрузить размеры лотов из файла."""
    lot_d = {}
    with open(("trade_instructions\\lot_size.txt"), 'r') as f:
        lines = f.readlines()
        i = 0
        for line in lines:
            if i > 0:
                line = line.replace('\n', '').split(',')
                symbol, lot = line[0], float(line[1])
                lot_d[symbol] = lot
            i += 1
    return lot_d


def rec_unrs_profit(time_, profit):
    """Записать непрогнозируемый профит."""
    with open("detected_profits.txt", 'a') as f:
        substr = str(time_) + ',' + str(profit) + '\n'
        f.write(substr)


def update_lims(d):
    """Проверить, нужно ли обновить лимиты на сегодня."""
    td = str(datetime.date.today())
    if td in d:
        return True
    else:
        print(f"{curr_time()} Обновление ценовых параметров")
        return False


# ═══ TELEGRAM ═══
def send_telegram(text: str, display_in_terminal: bool):
    """Отправить сообщение в Telegram (заглушка)."""
    if display_in_terminal:
        print(text)
    try:
        token = "5463006761:AAHtkpDczyJhwbgiInkxhIaE_4DPtR3BqyQ"
        channel_id = "-1001772302469"
        # r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
        #                   data={"chat_id": channel_id, "text": text})
        print('отправляем сообщение в тг (заглушка)')
    except Exception:
        print('tg error')


def show_start_msgs(advisor_id, now):
    """Вывести стартовые сообщения."""
    print(f'Запускаем алгоритм... Проверьте кнопку разрешения торговли в терминале')
    msg = f'Advisor ID = {advisor_id}. Время запуска (мск.время): ' + now.strftime("%d-%m-%Y %H:%M")
    send_telegram(msg, True)


# ═══ БЭКТЕСТ ═══
def _reconstruct_symbol_info(symbol, info_dict):
    """Восстановить объект с полями, которые нужны для бэктеста."""
    class _SymbolInfo:
        __slots__ = ['point', 'trade_tick_value', 'trade_tick_size', 'spread']
        def __init__(self, point, trade_tick_value, trade_tick_size, spread):
            self.point = point
            self.trade_tick_value = trade_tick_value
            self.trade_tick_size = trade_tick_size
            self.spread = spread
    return _SymbolInfo(info_dict['point'], info_dict['trade_tick_value'],
                       info_dict['trade_tick_size'], info_dict['spread'])


def _backtest_symbol(args):
    """Бэктест одного символа (для multiprocessing)."""
    (symbol_idx, symbol, df_window, info_dict, K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST,
     PARABOLIC_STEPS, PARABOLIC_MAXS, MA_PERIODS, RF_LOOKBACKS, RF_NBARS, RF_THRESHOLDS,
     LOGREG_LOOKBACKS, LOGREG_NBARS, LOGREG_THRESHOLDS,
     MACD_FAST_LIST, MACD_SLOW_LIST, MACD_SIGNAL_LIST, RSI_PERIOD_LIST,
     RSI_OVERSOLD_LIST, RSI_OVERBOUGHT_LIST,
     BB_PERIOD_LIST, BB_STD_LIST, VOLUME_PERIOD_LIST,
     EMA_FAST_LIST, EMA_SLOW_LIST,
     RSI_DIV_PERIOD_LIST, RSI_DIV_LOOKBACK_LIST, RSI_DIV_THRESHOLD_LIST,
     TENKAN_LIST, KIJUN_LIST, SENKOU_B_LIST, DISPLACEMENT_LIST,
     BACKTEST_DAYS, test_strategy, test_mode, total_symbols) = args

    # Восстановить объект "info" из примитивного словаря
    info = _reconstruct_symbol_info(symbol, info_dict)

    # Локальные backtest-функции (импортируются напрямую)
    from strategy_engine import calc_metrics, composite_score, deduplicate_results

    # Предрасчёт размеров
    stoch_per_symbol = len(K_PERIODS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    parab_per_symbol = len(PARABOLIC_STEPS) * len(PARABOLIC_MAXS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    ma_per_symbol = len(MA_PERIODS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    rf_per_symbol = len(RF_LOOKBACKS) * len(RF_NBARS) * len(RF_THRESHOLDS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    logreg_per_symbol = len(LOGREG_LOOKBACKS) * len(LOGREG_NBARS) * len(LOGREG_THRESHOLDS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)

    # Новые стратегии
    macd_rsi_per_symbol = len(MACD_FAST_LIST) * len(MACD_SLOW_LIST) * len(MACD_SIGNAL_LIST) * len(RSI_PERIOD_LIST) * len(RSI_OVERSOLD_LIST) * len(RSI_OVERBOUGHT_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    bollinger_per_symbol = len(BB_PERIOD_LIST) * len(BB_STD_LIST) * len(VOLUME_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    ema_cross_per_symbol = len(EMA_FAST_LIST) * len(EMA_SLOW_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    rsi_div_per_symbol = len(RSI_DIV_PERIOD_LIST) * len(RSI_DIV_LOOKBACK_LIST) * len(RSI_DIV_THRESHOLD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    ichimoku_per_symbol = len(TENKAN_LIST) * len(KIJUN_LIST) * len(SENKOU_B_LIST) * len(DISPLACEMENT_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)

    if test_strategy == 'stoch':
        active_combos = stoch_per_symbol
    elif test_strategy == 'parabolic':
        active_combos = parab_per_symbol
    elif test_strategy == 'ma':
        active_combos = ma_per_symbol
    elif test_strategy == 'rf':
        active_combos = rf_per_symbol
    elif test_strategy == 'logreg':
        active_combos = logreg_per_symbol
    elif test_strategy == 'macd_rsi':
        active_combos = macd_rsi_per_symbol
    elif test_strategy == 'bollinger':
        active_combos = bollinger_per_symbol
    elif test_strategy == 'ema_cross':
        active_combos = ema_cross_per_symbol
    elif test_strategy == 'rsi_div':
        active_combos = rsi_div_per_symbol
    elif test_strategy == 'ichimoku':
        active_combos = ichimoku_per_symbol
    else:
        active_combos = stoch_per_symbol + parab_per_symbol + ma_per_symbol + rf_per_symbol + logreg_per_symbol + macd_rsi_per_symbol + bollinger_per_symbol + ema_cross_per_symbol + rsi_div_per_symbol + ichimoku_per_symbol

    status = "старт" if symbol_idx < 4 else "в очереди"
    print(f"  [{symbol_idx + 1}/{total_symbols}] {symbol}: {status} ({active_combos} комб.)", flush=True)

    results = []
    combos_done = 0
    completed_strategies = []

    # ── Стохастик ──
    if not test_strategy or test_strategy == 'stoch':
        for i, (k, sl, tp) in enumerate(product(K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST), start=1):
            profit, n_trades, trade_profits = _backtest_stoch(
                df_window, k, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'stoch', 'k_period': k,
                'parabolic_max': None,
                'sl_points': sl, 'tp_points': tp,
                'profit': profit, 'n_trades': n_trades,
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'sharpe': metrics['sharpe'],
                'recovery': metrics['recovery'],
                'score': score,
            })
            combos_done += 1
        completed_strategies.append('Stoch')

    # ── Параболик ──
    if not test_strategy or test_strategy == 'parabolic':
        for i, (step, max_val, sl, tp) in enumerate(
            product(PARABOLIC_STEPS, PARABOLIC_MAXS, SL_POINTS_LIST, TP_POINTS_LIST),
            start=1
        ):
            profit, n_trades, trade_profits = _backtest_parabolic(
                df_window, step, max_val, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'parabolic', 'k_period': step,
                'parabolic_max': max_val,
                'sl_points': sl, 'tp_points': tp,
                'profit': profit, 'n_trades': n_trades,
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'sharpe': metrics['sharpe'],
                'recovery': metrics['recovery'],
                'score': score,
            })
            combos_done += 1
        completed_strategies.append('Parabolic')

    # ── Moving Average ──
    if not test_strategy or test_strategy == 'ma':
        for i, (ma_period, sl, tp) in enumerate(product(MA_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST), start=1):
            profit, n_trades, trade_profits = _backtest_ma(
                df_window, ma_period, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'ma', 'k_period': ma_period,
                'parabolic_max': None,
                'sl_points': sl, 'tp_points': tp,
                'profit': profit, 'n_trades': n_trades,
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'sharpe': metrics['sharpe'],
                'recovery': metrics['recovery'],
                'score': score,
            })
            combos_done += 1
        completed_strategies.append('MA')

    # ── Random Forest ──
    if not test_strategy or test_strategy == 'rf':
        for i, (lookback, n_bars, threshold, sl, tp) in enumerate(
            product(RF_LOOKBACKS, RF_NBARS, RF_THRESHOLDS, SL_POINTS_LIST, TP_POINTS_LIST),
            start=1
        ):
            profit, n_trades, trade_profits = _backtest_rf(
                df_window, lookback, n_bars, threshold, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                sim_lot=0.01, spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'rf',
                'k_period': f"lb{lookback}_nb{n_bars}_th{threshold:.2f}",
                'parabolic_max': None,
                'sl_points': sl, 'tp_points': tp,
                'profit': profit, 'n_trades': n_trades,
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'sharpe': metrics['sharpe'],
                'recovery': metrics['recovery'],
                'score': score,
            })
            combos_done += 1
        completed_strategies.append('RF')

    # ── Logistic Regression ──
    if not test_strategy or test_strategy == 'logreg':
        for i, (lookback, n_bars, threshold, sl, tp) in enumerate(
            product(LOGREG_LOOKBACKS, LOGREG_NBARS, LOGREG_THRESHOLDS, SL_POINTS_LIST, TP_POINTS_LIST),
            start=1
        ):
            profit, n_trades, trade_profits = _backtest_logreg(
                df_window, lookback, n_bars, threshold, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                sim_lot=0.01, spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'logreg',
                'k_period': f"lb{lookback}_nb{n_bars}_th{threshold:.2f}",
                'parabolic_max': None,
                'sl_points': sl, 'tp_points': tp,
                'profit': profit, 'n_trades': n_trades,
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'sharpe': metrics['sharpe'],
                'recovery': metrics['recovery'],
                'score': score,
            })
            combos_done += 1
        completed_strategies.append('LogReg')

    # ── MACD + RSI ──
    if not test_strategy or test_strategy == 'macd_rsi':
        for i, (mf, ms, msign, rp, ros, rob, sl, tp) in enumerate(
            product(MACD_FAST_LIST, MACD_SLOW_LIST, MACD_SIGNAL_LIST,
                    RSI_PERIOD_LIST, RSI_OVERSOLD_LIST, RSI_OVERBOUGHT_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _backtest_macd_rsi(
                df_window, mf, ms, msign, rp, ros, rob, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'macd_rsi',
                'k_period': f"mf{mf}_ms{ms}_rsi{rp}",
                'parabolic_max': None,
                'sl_points': sl, 'tp_points': tp,
                'profit': profit, 'n_trades': n_trades,
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'sharpe': metrics['sharpe'],
                'recovery': metrics['recovery'],
                'score': score,
            })
            combos_done += 1
        completed_strategies.append('MACD+RSI')

    # ── Bollinger Breakout ──
    if not test_strategy or test_strategy == 'bollinger':
        for i, (bp, bs, vp, sl, tp) in enumerate(
            product(BB_PERIOD_LIST, BB_STD_LIST, VOLUME_PERIOD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _backtest_bollinger(
                df_window, bp, bs, vp, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'bollinger',
                'k_period': f"bp{bp}_bs{bs}",
                'parabolic_max': None,
                'sl_points': sl, 'tp_points': tp,
                'profit': profit, 'n_trades': n_trades,
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'sharpe': metrics['sharpe'],
                'recovery': metrics['recovery'],
                'score': score,
            })
            combos_done += 1
        completed_strategies.append('Bollinger')

    # ── EMA Crossover ──
    if not test_strategy or test_strategy == 'ema_cross':
        for i, (ef, es, sl, tp) in enumerate(
            product(EMA_FAST_LIST, EMA_SLOW_LIST, SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _backtest_ema_crossover(
                df_window, ef, es, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'ema_cross',
                'k_period': f"ef{ef}_es{es}",
                'parabolic_max': None,
                'sl_points': sl, 'tp_points': tp,
                'profit': profit, 'n_trades': n_trades,
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'sharpe': metrics['sharpe'],
                'recovery': metrics['recovery'],
                'score': score,
            })
            combos_done += 1
        completed_strategies.append('EMA')

    # ── RSI Divergence ──
    if not test_strategy or test_strategy == 'rsi_div':
        for i, (rp, lb, th, sl, tp) in enumerate(
            product(RSI_DIV_PERIOD_LIST, RSI_DIV_LOOKBACK_LIST, RSI_DIV_THRESHOLD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _backtest_rsi_divergence(
                df_window, rp, lb, th, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'rsi_div',
                'k_period': f"rp{rp}_lb{lb}_th{th:.2f}",
                'parabolic_max': None,
                'sl_points': sl, 'tp_points': tp,
                'profit': profit, 'n_trades': n_trades,
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'sharpe': metrics['sharpe'],
                'recovery': metrics['recovery'],
                'score': score,
            })
            combos_done += 1
        completed_strategies.append('RSI-Div')

    # ── Ichimoku Cloud ──
    if not test_strategy or test_strategy == 'ichimoku':
        for i, (ten, kij, senk, disp, sl, tp) in enumerate(
            product(TENKAN_LIST, KIJUN_LIST, SENKOU_B_LIST, DISPLACEMENT_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _backtest_ichimoku(
                df_window, ten, kij, senk, disp, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'ichimoku',
                'k_period': f"ten{ten}_kij{kij}",
                'parabolic_max': None,
                'sl_points': sl, 'tp_points': tp,
                'profit': profit, 'n_trades': n_trades,
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'sharpe': metrics['sharpe'],
                'recovery': metrics['recovery'],
                'score': score,
            })
            combos_done += 1
        completed_strategies.append('Ichimoku')

    # ── Сохраняем чекпойнт после каждого символа ──
    # Вычисляем хеш данных для проверки обновления
    import hashlib
    data_hash = hashlib.md5(df_window.to_csv().encode()).hexdigest() if df_window is not None else None
    save_checkpoint(symbol, results, data_hash=data_hash)

    return symbol, results, combos_done, active_combos, completed_strategies



def run_full_backtest(SYMBOLS, symbol_data, K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST,
                      PARABOLIC_STEPS, PARABOLIC_MAXS, MA_PERIODS, RF_LOOKBACKS, RF_NBARS, RF_THRESHOLDS,
                      LOGREG_LOOKBACKS, LOGREG_NBARS, LOGREG_THRESHOLDS,
                      MACD_FAST_LIST, MACD_SLOW_LIST, MACD_SIGNAL_LIST, RSI_PERIOD_LIST,
                      RSI_OVERSOLD_LIST, RSI_OVERBOUGHT_LIST,
                      BB_PERIOD_LIST, BB_STD_LIST, VOLUME_PERIOD_LIST,
                      EMA_FAST_LIST, EMA_SLOW_LIST,
                      RSI_DIV_PERIOD_LIST, RSI_DIV_LOOKBACK_LIST, RSI_DIV_THRESHOLD_LIST,
                      TENKAN_LIST, KIJUN_LIST, SENKOU_B_LIST, DISPLACEMENT_LIST,
                      BACKTEST_DAYS, TOP_N,
                      test_strategy=None, test_mode=False, force_recalc=False):
    """Перебирает все комбинации stoch, parabolic, ma, rf, logreg. Возвращает (top, all).

    TOP_N — максимальное число стратегий на ОДНУ валюту.
    test_strategy — если задан, тестирует только одну стратегию.
    test_mode — если True, выводит спец-сообщение для тестового режима.
    force_recalc — если True, игнорирует чекпоинты и пересчитывает всё с нуля.
    """
    from strategy_engine import calc_metrics, composite_score, deduplicate_results

    all_results = []
    global_start = time.time()

    # Предрасчёт размеров
    stoch_per_symbol = len(K_PERIODS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    parab_per_symbol = len(PARABOLIC_STEPS) * len(PARABOLIC_MAXS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    ma_per_symbol = len(MA_PERIODS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    rf_per_symbol = len(RF_LOOKBACKS) * len(RF_NBARS) * len(RF_THRESHOLDS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    logreg_per_symbol = len(LOGREG_LOOKBACKS) * len(LOGREG_NBARS) * len(LOGREG_THRESHOLDS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)

    # Новые стратегии
    macd_rsi_per_symbol = (len(MACD_FAST_LIST) * len(MACD_SLOW_LIST) * len(MACD_SIGNAL_LIST) *
                           len(RSI_PERIOD_LIST) * len(RSI_OVERSOLD_LIST) * len(RSI_OVERBOUGHT_LIST) *
                           len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    bollinger_per_symbol = (len(BB_PERIOD_LIST) * len(BB_STD_LIST) * len(VOLUME_PERIOD_LIST) *
                            len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    ema_cross_per_symbol = (len(EMA_FAST_LIST) * len(EMA_SLOW_LIST) *
                            len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    rsi_div_per_symbol = (len(RSI_DIV_PERIOD_LIST) * len(RSI_DIV_LOOKBACK_LIST) *
                          len(RSI_DIV_THRESHOLD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    ichimoku_per_symbol = (len(TENKAN_LIST) * len(KIJUN_LIST) * len(SENKOU_B_LIST) *
                           len(DISPLACEMENT_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))

    # Фильтр по test_strategy
    if test_strategy == 'stoch':
        active_combos = stoch_per_symbol
    elif test_strategy == 'parabolic':
        active_combos = parab_per_symbol
    elif test_strategy == 'ma':
        active_combos = ma_per_symbol
    elif test_strategy == 'rf':
        active_combos = rf_per_symbol
    elif test_strategy == 'logreg':
        active_combos = logreg_per_symbol
    elif test_strategy == 'macd_rsi':
        active_combos = macd_rsi_per_symbol
    elif test_strategy == 'bollinger':
        active_combos = bollinger_per_symbol
    elif test_strategy == 'ema_cross':
        active_combos = ema_cross_per_symbol
    elif test_strategy == 'rsi_div':
        active_combos = rsi_div_per_symbol
    elif test_strategy == 'ichimoku':
        active_combos = ichimoku_per_symbol
    else:
        active_combos = (stoch_per_symbol + parab_per_symbol + ma_per_symbol + rf_per_symbol +
                         logreg_per_symbol + macd_rsi_per_symbol + bollinger_per_symbol +
                         ema_cross_per_symbol + rsi_div_per_symbol + ichimoku_per_symbol)

    combos_per_symbol = active_combos

    # ── Загружаем готовые чекпойнты ──
    existing_checkpoints = list_checkpoints()
    skipped_symbols = {}
    removed_stale = []
    for symbol in SYMBOLS:
        if force_recalc:
            # Принудительный пересчёт — удаляем все чекпоинты
            remove_checkpoint(symbol)
            continue
        if symbol in existing_checkpoints:
            cached = load_checkpoint(symbol)
            if cached is not None:
                # Проверяем, не обновились ли данные с момента сохранения чекпоинта
                if symbol in symbol_data:
                    df = symbol_data[symbol]['df_h1']
                    last_bar = df.index[-1]
                    checkpoint_path = _checkpoint_file(symbol)
                    try:
                        import hashlib
                        data_hash = hashlib.md5(df.to_csv().encode()).hexdigest()
                        # Сохраняем хеш данных в чекпоинте
                        with open(checkpoint_path, 'r', encoding='utf-8') as f:
                            cp_data = json.load(f)
                        if cp_data.get('data_hash') == data_hash:
                            # Данные не изменились — пропускаем
                            all_results.extend(cached)
                            skipped_symbols[symbol] = len(cached)
                        else:
                            # Данные обновились — удаляем чекпоинт и пересчитываем
                            remove_checkpoint(symbol)
                            removed_stale.append(symbol)
                    except (json.JSONDecodeError, KeyError):
                        # Неверный формат чекпоинта — пересчитываем
                        remove_checkpoint(symbol)
                        removed_stale.append(symbol)
                else:
                    all_results.extend(cached)
                    skipped_symbols[symbol] = len(cached)

    if skipped_symbols:
        print(f"\n  📦 Загружено из чекпойнтов {len(skipped_symbols)} символов:")
        for sym, n in skipped_symbols.items():
            print(f"    {sym}: {n} результатов")

    if removed_stale:
        print(f"\n  🔄 Обновлено {len(removed_stale)} чекпойнтов (данные обновились):")
        for sym in removed_stale:
            print(f"    {sym}")

    if force_recalc:
        print(f"\n  ⚡ Принудительный пересчёт — чекпоинты игнорируются")

    # ── Подготовить аргументы для каждого символа ──
    symbol_args = []
    valid_symbols = []
    for symbol in SYMBOLS:
        # Пропускаем символы с готовыми чекпойнтами
        if symbol in existing_checkpoints:
            continue
        if symbol not in symbol_data:
            continue
        sd = symbol_data[symbol]
        info = sd['info']
        # Извлечь только примитивные поля (SymbolInfo нельзя pickle)
        info_dict = {
            'point': info.point,
            'trade_tick_value': info.trade_tick_value,
            'trade_tick_size': info.trade_tick_size,
            'spread': info.spread,
        }
        df_window = sd['df_h1'].tail(BACKTEST_DAYS * 24)
        if len(df_window) < 30:
            print(f"  ⚠ {symbol}: мало данных ({len(df_window)} баров), пропускаем")
            continue
        valid_symbols.append(symbol)
        symbol_args.append((
            len(symbol_args), symbol, df_window, info_dict, K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST,
            PARABOLIC_STEPS, PARABOLIC_MAXS, MA_PERIODS, RF_LOOKBACKS, RF_NBARS, RF_THRESHOLDS,
            LOGREG_LOOKBACKS, LOGREG_NBARS, LOGREG_THRESHOLDS,
            MACD_FAST_LIST, MACD_SLOW_LIST, MACD_SIGNAL_LIST, RSI_PERIOD_LIST,
            RSI_OVERSOLD_LIST, RSI_OVERBOUGHT_LIST,
            BB_PERIOD_LIST, BB_STD_LIST, VOLUME_PERIOD_LIST,
            EMA_FAST_LIST, EMA_SLOW_LIST,
            RSI_DIV_PERIOD_LIST, RSI_DIV_LOOKBACK_LIST, RSI_DIV_THRESHOLD_LIST,
            TENKAN_LIST, KIJUN_LIST, SENKOU_B_LIST, DISPLACEMENT_LIST,
            BACKTEST_DAYS, test_strategy, test_mode, len(symbol_args)
        ))

    total_symbols = len(valid_symbols)
    total_combos = combos_per_symbol * total_symbols
    n_skipped = len(skipped_symbols)

    # ── Вывод плана бэктеста ──
    print(f"\n{'═' * 60}")
    if n_skipped > 0:
        print(f"  БЭКТЕСТ | {total_symbols} символов × {combos_per_symbol} комб. = {total_combos} всего")
        print(f"  ⏭ Пропущено (чекпойнт): {n_skipped} символов")
    else:
        print(f"  БЭКТЕСТ | {total_symbols} символов × {combos_per_symbol} комб. = {total_combos} всего")
    print(f"{'═' * 60}")

    # Какие стратегии считаются
    strategies_to_run = []
    if not test_strategy or test_strategy == 'stoch':
        strategies_to_run.append(f"Stoch: {stoch_per_symbol} комб.")
    if not test_strategy or test_strategy == 'parabolic':
        strategies_to_run.append(f"Parabolic: {parab_per_symbol} комб.")
    if not test_strategy or test_strategy == 'ma':
        strategies_to_run.append(f"MA: {ma_per_symbol} комб.")
    if not test_strategy or test_strategy == 'rf':
        strategies_to_run.append(f"RF: {rf_per_symbol} комб.")
    if not test_strategy or test_strategy == 'logreg':
        strategies_to_run.append(f"LogReg: {logreg_per_symbol} комб.")
    if not test_strategy or test_strategy == 'macd_rsi':
        strategies_to_run.append(f"MACD+RSI: {macd_rsi_per_symbol} комб.")
    if not test_strategy or test_strategy == 'bollinger':
        strategies_to_run.append(f"Bollinger: {bollinger_per_symbol} комб.")
    if not test_strategy or test_strategy == 'ema_cross':
        strategies_to_run.append(f"EMA: {ema_cross_per_symbol} комб.")
    if not test_strategy or test_strategy == 'rsi_div':
        strategies_to_run.append(f"RSI-Div: {rsi_div_per_symbol} комб.")
    if not test_strategy or test_strategy == 'ichimoku':
        strategies_to_run.append(f"Ichimoku: {ichimoku_per_symbol} комб.")

    print("  Стратегии на 1 символ:")
    for s in strategies_to_run:
        print(f"    {s}")

    if test_strategy:
        print(f"  ⚡ Только: '{test_strategy}'")
    elif test_mode:
        print(f"  ⚡ Тестовый режим (минимальный перебор)")

    print(f"\n  Символы ({total_symbols}): {', '.join(valid_symbols)}")
    print(f"  Окно данных: {BACKTEST_DAYS} дн. × 24 ч = {BACKTEST_DAYS * 24} баров")
    print(f"{'═' * 60}")

    n_processes = min(4, max(1, os.cpu_count() or 1))

    # Для 1 символа multiprocessing не нужен (spawn теряет stdout)
    if len(symbol_args) <= 1:
        use_multiprocessing = False
    else:
        use_multiprocessing = True

    # ── Запуск бэктеста ──
    results_list = []
    done = 0

    if use_multiprocessing:
        print(f"\n  Multiprocessing: {n_processes} процессов\n")
        import multiprocessing as mp
        with mp.Pool(processes=n_processes) as pool:
            for item in pool.imap_unordered(_backtest_symbol, symbol_args):
                results_list.append(item)
                done += 1
                # Распаковка результата
                symbol_done, results, combos_done, active_c, strats = item
                elapsed = time.time() - global_start
                print(f"\n  ✓ [{done}/{total_symbols}] {symbol_done} готово "
                      f"({combos_done} комб., {elapsed:.0f}с с начала)")
                for strat_name in strats:
                    print(f"    {symbol_done} | {strat_name} ✓")
    else:
        print(f"\n  Последовательный режим: {total_symbols} символов\n")
        for args in symbol_args:
            item = _backtest_symbol(args)
            results_list.append(item)
            done += 1
            symbol_done, results, combos_done, active_c, strats = item
            elapsed = time.time() - global_start
            print(f"\n  ✓ [{done}/{total_symbols}] {symbol_done} готово "
                  f"({combos_done} комб., {elapsed:.0f}с с начала)")
            for strat_name in strats:
                print(f"    {symbol_done} | {strat_name} ✓")

    # ── Собрать результаты ──
    all_results = []
    for item in results_list:
        symbol, results, combos_done, active_combos, completed_strategies = item
        all_results.extend(results)

    total_elapsed = time.time() - global_start
    print(f"\n{'─' * 60}")
    print(f"  Всего результатов: {len(all_results)}")
    print(f"  ⏱  Бэктест завершён за {total_elapsed:.0f}с ({total_elapsed / 60:.1f} мин)")

    # ── Дедупликация и сортировка ──
    print(f"\n  Дедупликация {len(all_results)} результатов...")
    all_results = deduplicate_results(all_results)
    all_results.sort(key=lambda x: x['score'], reverse=True)

    # Топ-N стратегий на каждую валюту
    top_results = []
    for symbol in SYMBOLS:
        symbol_strats = [r for r in all_results if r['symbol'] == symbol]
        top_results.extend(symbol_strats[:TOP_N])

    print(f"  Активных стратегий: {len(top_results)} ({TOP_N} на символ × {total_symbols} символов)")
    print(f"{'─' * 60}\n")

    # ── Чекпоинты НЕ удаляем — они ускоряют запуск, загружаясь при следующем старте ──

    return top_results, all_results

