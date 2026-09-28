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
    """Загрузить результаты для символа из чекпойнта. Возвращает (results, last_bar_time) или (None, None)."""
    path = _checkpoint_file(symbol)
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('results', []), data.get('last_bar_time')
    except (json.JSONDecodeError, KeyError):
        return None, None


def save_checkpoint(symbol, results, last_bar_time=None):
    """Сохранить результаты для символа в чекпойнт."""
    path = _checkpoint_file(symbol)
    data = {
        'symbol': symbol,
        'timestamp': datetime.datetime.now().isoformat(),
        'n_results': len(results),
        'last_bar_time': last_bar_time,
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
def _backtest_stoch(df, param_key, sl_points, tp_points, point, tick_value, tick_size, spread_points=0):
    """Backtest для Stochastic."""
    from strategies.stochastic import backtest as stoch_backtest
    return stoch_backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


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



def _backtest_macd_cross(df, macd_fast, macd_slow, macd_signal,
                         sl_points, tp_points, point, tick_value, tick_size, spread_points=0):
    """Backtest для MACD Crossover."""
    from strategies.macd_cross import backtest_macd_cross
    return backtest_macd_cross(df, macd_fast, macd_slow, macd_signal,
                               sl_points, tp_points, point, tick_value, tick_size,
                               sim_lot=0.01, spread_points=spread_points)


def _backtest_rsi_reversal(df, rsi_period, rsi_oversold, rsi_overbought,
                           sl_points, tp_points, point, tick_value, tick_size, spread_points=0):
    """Backtest для RSI Reversal."""
    from strategies.rsi_reversal import backtest_rsi_reversal
    return backtest_rsi_reversal(df, rsi_period, rsi_oversold, rsi_overbought,
                                 sl_points, tp_points, point, tick_value, tick_size,
                                 sim_lot=0.01, spread_points=spread_points)


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


def _backtest_zscore(df, sma_period, z_threshold, vol_period, sl_points, tp_points,
                     point, tick_value, tick_size, spread_points=0):
    """Backtest для Z-score reversion."""
    from strategies.zscore_reversion import backtest as backtest_zscore
    return backtest_zscore(df, sma_period, z_threshold, sl_points, tp_points, point,
                           tick_value, tick_size, vol_period=vol_period, sim_lot=0.01,
                           spread_points=spread_points)


def _backtest_autocorr(df, acf_lag, threshold, vol_period, sl_points, tp_points,
                       point, tick_value, tick_size, spread_points=0):
    """Backtest для Autocorrelation momentum."""
    from strategies.autocorrelation_momentum import backtest as backtest_autocorr
    return backtest_autocorr(df, acf_lag, threshold, sl_points, tp_points, point,
                             tick_value, tick_size, vol_period=vol_period, sim_lot=0.01,
                             spread_points=spread_points)


def _backtest_hurst(df, window, trend_threshold, vol_period, sl_points, tp_points,
                    point, tick_value, tick_size, spread_points=0):
    """Backtest для Hurst regime filter."""
    from strategies.hurst_regime_filter import backtest as backtest_hurst
    return backtest_hurst(df, window, trend_threshold, 0.5, sl_points, tp_points, point,
                          tick_value, tick_size, vol_period=vol_period, sim_lot=0.01,
                          spread_points=spread_points)


def _backtest_lrc(df, period, std_threshold, vol_period, sl_points, tp_points,
                  point, tick_value, tick_size, spread_points=0):
    """Backtest для Linear Regression Channel."""
    from strategies.linear_regression_channel import backtest as backtest_lrc
    return backtest_lrc(df, period, std_threshold, sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot=0.01,
                        spread_points=spread_points)


def _backtest_percentile(df, period, pct_low, pct_high, vol_period, sl_points, tp_points,
                         point, tick_value, tick_size, spread_points=0):
    """Backtest для Percentile reversion."""
    from strategies.percentile_reversion import backtest as backtest_percentile
    return backtest_percentile(df, period, pct_low, pct_high, 50.0, sl_points, tp_points, point,
                               tick_value, tick_size, sim_lot=0.01,
                               spread_points=spread_points)


def _backtest_runs(df, window, threshold, vol_period, sl_points, tp_points,
                   point, tick_value, tick_size, spread_points=0):
    """Backtest для Runs Test trend."""
    from strategies.runs_test_trend import backtest as backtest_runs
    return backtest_runs(df, window, threshold, sl_points, tp_points, point,
                         tick_value, tick_size, sim_lot=0.01,
                         spread_points=spread_points)


def _backtest_coint(df, window, threshold, beta_period, sl_points, tp_points,
                    point, tick_value, tick_size, spread_points=0):
    """Backtest для Cointegration pairs."""
    from strategies.cointegration_pairs import backtest as backtest_coint
    return backtest_coint(df, window, threshold, 0.0, sl_points, tp_points, point,
                          tick_value, tick_size, sim_lot=0.01,
                          spread_points=spread_points)


def _backtest_sharpe(df, window, threshold, vol_period, sl_points, tp_points,
                     point, tick_value, tick_size, spread_points=0):
    """Backtest для Rolling Sharpe filter."""
    from strategies.rolling_sharpe_filter import backtest as backtest_sharpe
    return backtest_sharpe(df, window, threshold, 0.0, sl_points, tp_points, point,
                           tick_value, tick_size, sim_lot=0.01,
                           spread_points=spread_points)


def _backtest_skewness(df, window, threshold, vol_period, sl_points, tp_points,
                       point, tick_value, tick_size, spread_points=0):
    """Backtest для Skewness extreme."""
    from strategies.skewness_extreme import backtest as backtest_skewness
    return backtest_skewness(df, window, threshold, 0.3, sl_points, tp_points, point,
                             tick_value, tick_size, sim_lot=0.01,
                             spread_points=spread_points)


def _backtest_bayesian(df, window, threshold, prior, sl_points, tp_points,
                       point, tick_value, tick_size, spread_points=0):
    """Backtest для Bayesian trend update."""
    from strategies.bayesian_trend_update import backtest as backtest_bayesian
    return backtest_bayesian(df, window, prior, threshold, 0.5, sl_points, tp_points, point,
                             tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_kurtosis(df, window, threshold, vol_period, sl_points, tp_points,
                       point, tick_value, tick_size, spread_points=0):
    """Backtest для Kurtosis spike."""
    from strategies.kurtosis_spike import backtest as backtest_kurtosis
    return backtest_kurtosis(df, window, threshold, 3.0, 1.0, sl_points, tp_points, point,
                             tick_value, tick_size, sim_lot=0.01,
                             spread_points=spread_points)


def _backtest_chi_square(df, window, entry_threshold, exit_threshold, vol_period,
                         sl_points, tp_points, point, tick_value, tick_size, spread_points=0):
    """Backtest для Chi-square distribution."""
    from strategies.chi_square_distribution import backtest as backtest_chi_square
    return backtest_chi_square(df, window, entry_threshold, exit_threshold, sl_points,
                               tp_points, point, tick_value, tick_size,
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
     MACD_CROSS_FAST_LIST, MACD_CROSS_SLOW_LIST, MACD_CROSS_SIGNAL_LIST,
     RSI_REV_PERIOD_LIST, RSI_REV_OVERSOLD_LIST, RSI_REV_OVERBOUGHT_LIST,
     BB_PERIOD_LIST, BB_STD_LIST, VOLUME_PERIOD_LIST,
     EMA_FAST_LIST, EMA_SLOW_LIST,
     RSI_DIV_PERIOD_LIST, RSI_DIV_LOOKBACK_LIST, RSI_DIV_THRESHOLD_LIST,
     TENKAN_LIST, KIJUN_LIST, SENKOU_B_LIST, DISPLACEMENT_LIST,
     ZSCORE_SMA_PERIOD_LIST, ZSCORE_THRESHOLD_LIST, ZSCORE_VOL_PERIOD_LIST,
     AUTOCORR_LAG_LIST, AUTOCORR_THRESHOLD_LIST, AUTOCORR_VOL_PERIOD_LIST,
     HURST_WINDOW_LIST, HURST_TREND_THRESHOLD_LIST, HURST_VOL_PERIOD_LIST,
     LRC_PERIOD_LIST, LRC_STD_THRESHOLD_LIST, LRC_VOL_PERIOD_LIST,
     PCT_PERIOD_LIST, PCT_LOW_LIST, PCT_HIGH_LIST, PCT_VOL_PERIOD_LIST,
     RUNS_WINDOW_LIST, RUNS_THRESHOLD_LIST, RUNS_VOL_PERIOD_LIST,
     COINT_WINDOW_LIST, COINT_THRESHOLD_LIST, COINT_BETA_PERIOD_LIST,
     SHARPE_WINDOW_LIST, SHARPE_THRESHOLD_LIST, SHARPE_VOL_PERIOD_LIST,
     SKEW_WINDOW_LIST, SKEW_THRESHOLD_LIST, SKEW_VOL_PERIOD_LIST,
     BAYES_WINDOW_LIST, BAYES_THRESHOLD_LIST, BAYES_PRIOR_LIST,
     KURT_WINDOW_LIST, KURT_THRESHOLD_LIST, KURT_VOL_PERIOD_LIST,
     CHISQ_WINDOW_LIST, CHISQ_ENTRY_LIST, CHISQ_EXIT_LIST, CHISQ_VOL_PERIOD_LIST,
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
    macd_cross_per_symbol = (len(MACD_CROSS_FAST_LIST) * len(MACD_CROSS_SLOW_LIST) *
                             len(MACD_CROSS_SIGNAL_LIST) *
                             len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    rsi_rev_per_symbol = (len(RSI_REV_PERIOD_LIST) * len(RSI_REV_OVERSOLD_LIST) *
                          len(RSI_REV_OVERBOUGHT_LIST) *
                          len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
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
    elif test_strategy == 'macd_cross':
        active_combos = macd_cross_per_symbol
    elif test_strategy == 'rsi_rev':
        active_combos = rsi_rev_per_symbol
    elif test_strategy == 'bollinger':
        active_combos = bollinger_per_symbol
    elif test_strategy == 'ema_cross':
        active_combos = ema_cross_per_symbol
    elif test_strategy == 'rsi_div':
        active_combos = rsi_div_per_symbol
    elif test_strategy == 'ichimoku':
        active_combos = ichimoku_per_symbol
    else:
        active_combos = (stoch_per_symbol + parab_per_symbol + ma_per_symbol + rf_per_symbol + logreg_per_symbol +
                         macd_cross_per_symbol + rsi_rev_per_symbol + bollinger_per_symbol +
                         ema_cross_per_symbol + rsi_div_per_symbol + ichimoku_per_symbol)

    status = "старт" if symbol_idx < 4 else "в очереди"
    print(f"  [{symbol_idx + 1}/{total_symbols}] {symbol}: {status} ({active_combos} комб.)", flush=True)

    results = []
    combos_done = 0
    completed_strategies = []

    # ── Обёртка для безопасного бэктеста ──
    def _safe_backtest(strategy_name, bt_fn, *args, **kwargs):
        """Безопасный вызов бэктеста — ловит ошибки, не прерывая весь процесс."""
        nonlocal combos_done
        try:
            return bt_fn(*args, **kwargs)
        except Exception as e:
            print(f"  [ERROR] {symbol} | {strategy_name}: {e}", flush=True)
            return 0, 0, []

    # ── Стохастик ──
    if not test_strategy or test_strategy == 'stoch':
        for i, (k, sl, tp) in enumerate(product(K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST), start=1):
            profit, n_trades, trade_profits = _safe_backtest(
                'Stochastic', _backtest_stoch,
                df_window, k, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'stoch', 'param_key': k,
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
            profit, n_trades, trade_profits = _safe_backtest('Parabolic', _backtest_parabolic,
                df_window, step, max_val, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'parabolic', 'param_key': step,
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
            profit, n_trades, trade_profits = _safe_backtest('MA', _backtest_ma,
                df_window, ma_period, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'ma', 'param_key': ma_period,
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
            profit, n_trades, trade_profits = _safe_backtest('RF', _backtest_rf,
                df_window, lookback, n_bars, threshold, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                sim_lot=0.01, spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'rf',
                'param_key': f"lb{lookback}_nb{n_bars}_th{threshold:.2f}",
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
            profit, n_trades, trade_profits = _safe_backtest('LogReg', _backtest_logreg,
                df_window, lookback, n_bars, threshold, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                sim_lot=0.01, spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'logreg',
                'param_key': f"lb{lookback}_nb{n_bars}_th{threshold:.2f}",
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


    # ── MACD Cross ──
    if not test_strategy or test_strategy == 'macd_cross':
        for i, (mf, ms, msig, sl, tp) in enumerate(
            product(MACD_CROSS_FAST_LIST, MACD_CROSS_SLOW_LIST, MACD_CROSS_SIGNAL_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('MACD-Cross', _backtest_macd_cross,
                df_window, mf, ms, msig, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'macd_cross',
                'param_key': f"mf{mf}_ms{ms}_sig{msig}",
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
        completed_strategies.append('MACD-Cross')

    # ── RSI Reversal ──
    if not test_strategy or test_strategy == 'rsi_rev':
        for i, (rp, ros, rob, sl, tp) in enumerate(
            product(RSI_REV_PERIOD_LIST, RSI_REV_OVERSOLD_LIST, RSI_REV_OVERBOUGHT_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('RSI-Rev', _backtest_rsi_reversal,
                df_window, rp, ros, rob, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'rsi_rev',
                'param_key': f"rp{rp}_ros{ros}_rob{rob}",
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
        completed_strategies.append('RSI-Rev')

    # ── Bollinger Breakout ──
    if not test_strategy or test_strategy == 'bollinger':
        for i, (bp, bs, vp, sl, tp) in enumerate(
            product(BB_PERIOD_LIST, BB_STD_LIST, VOLUME_PERIOD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('Bollinger', _backtest_bollinger,
                df_window, bp, bs, vp, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'bollinger',
                'param_key': f"bp{bp}_bs{bs}",
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
            profit, n_trades, trade_profits = _safe_backtest('EMA', _backtest_ema_crossover,
                df_window, ef, es, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'ema_cross',
                'param_key': f"ef{ef}_es{es}",
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
            profit, n_trades, trade_profits = _safe_backtest('RSI-Div', _backtest_rsi_divergence,
                df_window, rp, lb, th, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'rsi_div',
                'param_key': f"rp{rp}_lb{lb}_th{th:.2f}",
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
            profit, n_trades, trade_profits = _safe_backtest('Ichimoku', _backtest_ichimoku,
                df_window, ten, kij, senk, disp, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'ichimoku',
                'param_key': f"ten{ten}_kij{kij}",
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

    # ── Z-score reversion ──
    if not test_strategy or test_strategy == 'zscore':
        for i, (sma_p, z_th, vol_p, sl, tp) in enumerate(
            product(ZSCORE_SMA_PERIOD_LIST, ZSCORE_THRESHOLD_LIST, ZSCORE_VOL_PERIOD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('Zscore', _backtest_zscore,
                df_window, sma_p, z_th, vol_p, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'zscore',
                'param_key': f"sma{sma_p}_z{z_th:.1f}",
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
        completed_strategies.append('Zscore')

    # ── Autocorrelation momentum ──
    if not test_strategy or test_strategy == 'autocorr':
        for i, (acf_lag, acf_th, vol_p, sl, tp) in enumerate(
            product(AUTOCORR_LAG_LIST, AUTOCORR_THRESHOLD_LIST, AUTOCORR_VOL_PERIOD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('Autocorr', _backtest_autocorr,
                df_window, acf_lag, acf_th, vol_p, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'autocorr',
                'param_key': f"lag{acf_lag}_th{acf_th:.2f}",
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
        completed_strategies.append('Autocorr')

    # ── Hurst regime filter ──
    if not test_strategy or test_strategy == 'hurst':
        for i, (win, trend_th, vol_p, sl, tp) in enumerate(
            product(HURST_WINDOW_LIST, HURST_TREND_THRESHOLD_LIST, HURST_VOL_PERIOD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('Hurst', _backtest_hurst,
                df_window, win, trend_th, vol_p, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'hurst',
                'param_key': f"win{win}_th{trend_th:.2f}",
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
        completed_strategies.append('Hurst')

    # ── Linear Regression Channel ──
    if not test_strategy or test_strategy == 'lrc':
        for i, (period, std_th, vol_p, sl, tp) in enumerate(
            product(LRC_PERIOD_LIST, LRC_STD_THRESHOLD_LIST, LRC_VOL_PERIOD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('LRC', _backtest_lrc,
                df_window, period, std_th, vol_p, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'lrc',
                'param_key': f"per{period}_std{std_th:.1f}",
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
        completed_strategies.append('LRC')

    # ── Percentile reversion ──
    if not test_strategy or test_strategy == 'percentile':
        for i, (per, pct_l, pct_h, vol_p, sl, tp) in enumerate(
            product(PCT_PERIOD_LIST, PCT_LOW_LIST, PCT_HIGH_LIST, PCT_VOL_PERIOD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('Percentile', _backtest_percentile,
                df_window, per, pct_l, pct_h, vol_p, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'percentile',
                'param_key': f"per{per}_l{pct_l}_h{pct_h}",
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
        completed_strategies.append('Percentile')

    # ── Runs Test trend ──
    if not test_strategy or test_strategy == 'runs':
        for i, (win, runs_th, vol_p, sl, tp) in enumerate(
            product(RUNS_WINDOW_LIST, RUNS_THRESHOLD_LIST, RUNS_VOL_PERIOD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('Runs', _backtest_runs,
                df_window, win, runs_th, vol_p, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'runs',
                'param_key': f"win{win}_th{runs_th:.1f}",
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
        completed_strategies.append('Runs')

    # ── Cointegration pairs ──
    if not test_strategy or test_strategy == 'coint':
        for i, (win, coint_th, beta_p, sl, tp) in enumerate(
            product(COINT_WINDOW_LIST, COINT_THRESHOLD_LIST, COINT_BETA_PERIOD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('Coint', _backtest_coint,
                df_window, win, coint_th, beta_p, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'coint',
                'param_key': f"win{win}_th{coint_th:.1f}",
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
        completed_strategies.append('Coint')

    # ── Rolling Sharpe filter ──
    if not test_strategy or test_strategy == 'sharpe':
        for i, (win, sharpe_th, vol_p, sl, tp) in enumerate(
            product(SHARPE_WINDOW_LIST, SHARPE_THRESHOLD_LIST, SHARPE_VOL_PERIOD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('Sharpe', _backtest_sharpe,
                df_window, win, sharpe_th, vol_p, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'sharpe',
                'param_key': f"win{win}_th{sharpe_th:.2f}",
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
        completed_strategies.append('Sharpe')

    # ── Skewness extreme ──
    if not test_strategy or test_strategy == 'skewness':
        for i, (win, skew_th, vol_p, sl, tp) in enumerate(
            product(SKEW_WINDOW_LIST, SKEW_THRESHOLD_LIST, SKEW_VOL_PERIOD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('Skewness', _backtest_skewness,
                df_window, win, skew_th, vol_p, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'skewness',
                'param_key': f"win{win}_th{skew_th:.1f}",
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
        completed_strategies.append('Skewness')

    # ── Bayesian trend update ──
    if not test_strategy or test_strategy == 'bayesian':
        for i, (win, bay_th, prior, sl, tp) in enumerate(
            product(BAYES_WINDOW_LIST, BAYES_THRESHOLD_LIST, BAYES_PRIOR_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('Bayesian', _backtest_bayesian,
                df_window, win, bay_th, prior, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'bayesian',
                'param_key': f"win{win}_th{bay_th:.2f}",
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
        completed_strategies.append('Bayesian')

    # ── Kurtosis spike ──
    if not test_strategy or test_strategy == 'kurtosis':
        for i, (win, kurt_th, vol_p, sl, tp) in enumerate(
            product(KURT_WINDOW_LIST, KURT_THRESHOLD_LIST, KURT_VOL_PERIOD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('Kurtosis', _backtest_kurtosis,
                df_window, win, kurt_th, vol_p, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'kurtosis',
                'param_key': f"win{win}_th{kurt_th:.1f}",
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
        completed_strategies.append('Kurtosis')

    # ── Chi-square distribution ──
    if not test_strategy or test_strategy == 'chi_square':
        for i, (win, entry_th, exit_th, vol_p, sl, tp) in enumerate(
            product(CHISQ_WINDOW_LIST, CHISQ_ENTRY_LIST, CHISQ_EXIT_LIST, CHISQ_VOL_PERIOD_LIST,
                    SL_POINTS_LIST, TP_POINTS_LIST), start=1
        ):
            profit, n_trades, trade_profits = _safe_backtest('ChiSq', _backtest_chi_square,
                df_window, win, entry_th, exit_th, vol_p, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'chi_square',
                'param_key': f"win{win}_e{entry_th:.2f}_x{exit_th:.2f}",
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
        completed_strategies.append('ChiSq')

    # ── Сохраняем чекпойнт после каждого символа ──
    last_bar_time = df_window.index[-1].isoformat() if df_window is not None else None
    save_checkpoint(symbol, results, last_bar_time=last_bar_time)

    return symbol, results, combos_done, active_combos, completed_strategies



def run_full_backtest(SYMBOLS, symbol_data, K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST,
                      PARABOLIC_STEPS, PARABOLIC_MAXS, MA_PERIODS, RF_LOOKBACKS, RF_NBARS, RF_THRESHOLDS,
                      LOGREG_LOOKBACKS, LOGREG_NBARS, LOGREG_THRESHOLDS,
                      MACD_CROSS_FAST_LIST, MACD_CROSS_SLOW_LIST, MACD_CROSS_SIGNAL_LIST,
                      RSI_REV_PERIOD_LIST, RSI_REV_OVERSOLD_LIST, RSI_REV_OVERBOUGHT_LIST,
                      BB_PERIOD_LIST, BB_STD_LIST, VOLUME_PERIOD_LIST,
                      EMA_FAST_LIST, EMA_SLOW_LIST,
                      RSI_DIV_PERIOD_LIST, RSI_DIV_LOOKBACK_LIST, RSI_DIV_THRESHOLD_LIST,
                      TENKAN_LIST, KIJUN_LIST, SENKOU_B_LIST, DISPLACEMENT_LIST,
                      ZSCORE_SMA_PERIOD_LIST, ZSCORE_THRESHOLD_LIST, ZSCORE_VOL_PERIOD_LIST,
                      AUTOCORR_LAG_LIST, AUTOCORR_THRESHOLD_LIST, AUTOCORR_VOL_PERIOD_LIST,
                      HURST_WINDOW_LIST, HURST_TREND_THRESHOLD_LIST, HURST_VOL_PERIOD_LIST,
                      LRC_PERIOD_LIST, LRC_STD_THRESHOLD_LIST, LRC_VOL_PERIOD_LIST,
                      PCT_PERIOD_LIST, PCT_LOW_LIST, PCT_HIGH_LIST, PCT_VOL_PERIOD_LIST,
                      RUNS_WINDOW_LIST, RUNS_THRESHOLD_LIST, RUNS_VOL_PERIOD_LIST,
                      COINT_WINDOW_LIST, COINT_THRESHOLD_LIST, COINT_BETA_PERIOD_LIST,
                      SHARPE_WINDOW_LIST, SHARPE_THRESHOLD_LIST, SHARPE_VOL_PERIOD_LIST,
                      SKEW_WINDOW_LIST, SKEW_THRESHOLD_LIST, SKEW_VOL_PERIOD_LIST,
                      BAYES_WINDOW_LIST, BAYES_THRESHOLD_LIST, BAYES_PRIOR_LIST,
                      KURT_WINDOW_LIST, KURT_THRESHOLD_LIST, KURT_VOL_PERIOD_LIST,
                      CHISQ_WINDOW_LIST, CHISQ_ENTRY_LIST, CHISQ_EXIT_LIST, CHISQ_VOL_PERIOD_LIST,
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
    macd_cross_per_symbol = (len(MACD_CROSS_FAST_LIST) * len(MACD_CROSS_SLOW_LIST) *
                             len(MACD_CROSS_SIGNAL_LIST) *
                             len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    rsi_rev_per_symbol = (len(RSI_REV_PERIOD_LIST) * len(RSI_REV_OVERSOLD_LIST) *
                          len(RSI_REV_OVERBOUGHT_LIST) *
                          len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    bollinger_per_symbol = (len(BB_PERIOD_LIST) * len(BB_STD_LIST) * len(VOLUME_PERIOD_LIST) *
                            len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    ema_cross_per_symbol = (len(EMA_FAST_LIST) * len(EMA_SLOW_LIST) *
                            len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    rsi_div_per_symbol = (len(RSI_DIV_PERIOD_LIST) * len(RSI_DIV_LOOKBACK_LIST) *
                          len(RSI_DIV_THRESHOLD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    ichimoku_per_symbol = (len(TENKAN_LIST) * len(KIJUN_LIST) * len(SENKOU_B_LIST) *
                           len(DISPLACEMENT_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))

    # STANDALONE стратегии
    zscore_per_symbol = (len(ZSCORE_SMA_PERIOD_LIST) * len(ZSCORE_THRESHOLD_LIST) *
                         len(ZSCORE_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    autocorr_per_symbol = (len(AUTOCORR_LAG_LIST) * len(AUTOCORR_THRESHOLD_LIST) *
                           len(AUTOCORR_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    hurst_per_symbol = (len(HURST_WINDOW_LIST) * len(HURST_TREND_THRESHOLD_LIST) *
                        len(HURST_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    lrc_per_symbol = (len(LRC_PERIOD_LIST) * len(LRC_STD_THRESHOLD_LIST) *
                      len(LRC_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    percentile_per_symbol = (len(PCT_PERIOD_LIST) * len(PCT_LOW_LIST) * len(PCT_HIGH_LIST) *
                             len(PCT_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    runs_per_symbol = (len(RUNS_WINDOW_LIST) * len(RUNS_THRESHOLD_LIST) *
                       len(RUNS_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    coint_per_symbol = (len(COINT_WINDOW_LIST) * len(COINT_THRESHOLD_LIST) *
                        len(COINT_BETA_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    sharpe_per_symbol = (len(SHARPE_WINDOW_LIST) * len(SHARPE_THRESHOLD_LIST) *
                         len(SHARPE_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    skewness_per_symbol = (len(SKEW_WINDOW_LIST) * len(SKEW_THRESHOLD_LIST) *
                           len(SKEW_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    bayesian_per_symbol = (len(BAYES_WINDOW_LIST) * len(BAYES_THRESHOLD_LIST) *
                           len(BAYES_PRIOR_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    kurtosis_per_symbol = (len(KURT_WINDOW_LIST) * len(KURT_THRESHOLD_LIST) *
                           len(KURT_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    chi_square_per_symbol = (len(CHISQ_WINDOW_LIST) * len(CHISQ_ENTRY_LIST) *
                             len(CHISQ_EXIT_LIST) * len(CHISQ_VOL_PERIOD_LIST) *
                             len(SL_POINTS_LIST) * len(TP_POINTS_LIST))

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
    elif test_strategy == 'macd_cross':
        active_combos = macd_cross_per_symbol
    elif test_strategy == 'rsi_rev':
        active_combos = rsi_rev_per_symbol
    elif test_strategy == 'bollinger':
        active_combos = bollinger_per_symbol
    elif test_strategy == 'ema_cross':
        active_combos = ema_cross_per_symbol
    elif test_strategy == 'rsi_div':
        active_combos = rsi_div_per_symbol
    elif test_strategy == 'ichimoku':
        active_combos = ichimoku_per_symbol
    elif test_strategy == 'zscore':
        active_combos = zscore_per_symbol
    elif test_strategy == 'autocorr':
        active_combos = autocorr_per_symbol
    elif test_strategy == 'hurst':
        active_combos = hurst_per_symbol
    elif test_strategy == 'lrc':
        active_combos = lrc_per_symbol
    elif test_strategy == 'percentile':
        active_combos = percentile_per_symbol
    elif test_strategy == 'runs':
        active_combos = runs_per_symbol
    elif test_strategy == 'coint':
        active_combos = coint_per_symbol
    elif test_strategy == 'sharpe':
        active_combos = sharpe_per_symbol
    elif test_strategy == 'skewness':
        active_combos = skewness_per_symbol
    elif test_strategy == 'bayesian':
        active_combos = bayesian_per_symbol
    elif test_strategy == 'kurtosis':
        active_combos = kurtosis_per_symbol
    elif test_strategy == 'chi_square':
        active_combos = chi_square_per_symbol
    else:
        active_combos = (stoch_per_symbol + parab_per_symbol + ma_per_symbol + rf_per_symbol + logreg_per_symbol +
                         macd_cross_per_symbol + rsi_rev_per_symbol + bollinger_per_symbol + ema_cross_per_symbol +
                         rsi_div_per_symbol + ichimoku_per_symbol + zscore_per_symbol + autocorr_per_symbol +
                         hurst_per_symbol + lrc_per_symbol + percentile_per_symbol + runs_per_symbol +
                         coint_per_symbol + sharpe_per_symbol + skewness_per_symbol + bayesian_per_symbol +
                         kurtosis_per_symbol + chi_square_per_symbol)

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
            cached, cached_bar_time = load_checkpoint(symbol)
            if cached is not None and symbol in symbol_data:
                df = symbol_data[symbol]['df_h1']
                current_bar_time = df.index[-1].isoformat()
                if cached_bar_time == current_bar_time:
                    # Данные не изменились — пропускаем
                    all_results.extend(cached)
                    skipped_symbols[symbol] = len(cached)
                else:
                    # Данные обновились — удаляем чекпоинт и пересчитываем
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

    # ── Сначала собрать valid_symbols ──
    valid_symbols = []
    for symbol in SYMBOLS:
        # Пропускаем символы с готовыми чекпойнтами
        if symbol in skipped_symbols:
            continue
        if symbol not in symbol_data:
            continue
        sd = symbol_data[symbol]
        df_window = sd['df_h1'].tail(BACKTEST_DAYS * 24)
        if len(df_window) < 30:
            print(f"  ⚠ {symbol}: мало данных ({len(df_window)} баров), пропускаем")
            continue
        valid_symbols.append(symbol)

    total_symbols = len(valid_symbols)

    # ── Теперь собрать args с правильным total_symbols ──
    symbol_args = []
    for idx, symbol in enumerate(valid_symbols):
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
        symbol_args.append((
            idx, symbol, df_window, info_dict, K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST,
            PARABOLIC_STEPS, PARABOLIC_MAXS, MA_PERIODS, RF_LOOKBACKS, RF_NBARS, RF_THRESHOLDS,
            LOGREG_LOOKBACKS, LOGREG_NBARS, LOGREG_THRESHOLDS,
            MACD_CROSS_FAST_LIST, MACD_CROSS_SLOW_LIST, MACD_CROSS_SIGNAL_LIST,
            RSI_REV_PERIOD_LIST, RSI_REV_OVERSOLD_LIST, RSI_REV_OVERBOUGHT_LIST,
            BB_PERIOD_LIST, BB_STD_LIST, VOLUME_PERIOD_LIST,
            EMA_FAST_LIST, EMA_SLOW_LIST,
            RSI_DIV_PERIOD_LIST, RSI_DIV_LOOKBACK_LIST, RSI_DIV_THRESHOLD_LIST,
            TENKAN_LIST, KIJUN_LIST, SENKOU_B_LIST, DISPLACEMENT_LIST,
            ZSCORE_SMA_PERIOD_LIST, ZSCORE_THRESHOLD_LIST, ZSCORE_VOL_PERIOD_LIST,
            AUTOCORR_LAG_LIST, AUTOCORR_THRESHOLD_LIST, AUTOCORR_VOL_PERIOD_LIST,
            HURST_WINDOW_LIST, HURST_TREND_THRESHOLD_LIST, HURST_VOL_PERIOD_LIST,
            LRC_PERIOD_LIST, LRC_STD_THRESHOLD_LIST, LRC_VOL_PERIOD_LIST,
            PCT_PERIOD_LIST, PCT_LOW_LIST, PCT_HIGH_LIST, PCT_VOL_PERIOD_LIST,
            RUNS_WINDOW_LIST, RUNS_THRESHOLD_LIST, RUNS_VOL_PERIOD_LIST,
            COINT_WINDOW_LIST, COINT_THRESHOLD_LIST, COINT_BETA_PERIOD_LIST,
            SHARPE_WINDOW_LIST, SHARPE_THRESHOLD_LIST, SHARPE_VOL_PERIOD_LIST,
            SKEW_WINDOW_LIST, SKEW_THRESHOLD_LIST, SKEW_VOL_PERIOD_LIST,
            BAYES_WINDOW_LIST, BAYES_THRESHOLD_LIST, BAYES_PRIOR_LIST,
            KURT_WINDOW_LIST, KURT_THRESHOLD_LIST, KURT_VOL_PERIOD_LIST,
            CHISQ_WINDOW_LIST, CHISQ_ENTRY_LIST, CHISQ_EXIT_LIST, CHISQ_VOL_PERIOD_LIST,
            BACKTEST_DAYS, test_strategy, test_mode, total_symbols
        ))
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
    if not test_strategy or test_strategy == 'bollinger':
        strategies_to_run.append(f"Bollinger: {bollinger_per_symbol} комб.")
    if not test_strategy or test_strategy == 'ema_cross':
        strategies_to_run.append(f"EMA: {ema_cross_per_symbol} комб.")
    if not test_strategy or test_strategy == 'rsi_div':
        strategies_to_run.append(f"RSI-Div: {rsi_div_per_symbol} комб.")
    if not test_strategy or test_strategy == 'ichimoku':
        strategies_to_run.append(f"Ichimoku: {ichimoku_per_symbol} комб.")
    if not test_strategy or test_strategy == 'macd_cross':
        strategies_to_run.append(f"MACD-Cross: {macd_cross_per_symbol} комб.")
    if not test_strategy or test_strategy == 'rsi_rev':
        strategies_to_run.append(f"RSI-Rev: {rsi_rev_per_symbol} комб.")
    if not test_strategy or test_strategy == 'zscore':
        strategies_to_run.append(f"Zscore: {zscore_per_symbol} комб.")
    if not test_strategy or test_strategy == 'autocorr':
        strategies_to_run.append(f"Autocorr: {autocorr_per_symbol} комб.")
    if not test_strategy or test_strategy == 'hurst':
        strategies_to_run.append(f"Hurst: {hurst_per_symbol} комб.")
    if not test_strategy or test_strategy == 'lrc':
        strategies_to_run.append(f"LRC: {lrc_per_symbol} комб.")
    if not test_strategy or test_strategy == 'percentile':
        strategies_to_run.append(f"Percentile: {percentile_per_symbol} комб.")
    if not test_strategy or test_strategy == 'runs':
        strategies_to_run.append(f"Runs: {runs_per_symbol} комб.")
    if not test_strategy or test_strategy == 'coint':
        strategies_to_run.append(f"Coint: {coint_per_symbol} комб.")
    if not test_strategy or test_strategy == 'sharpe':
        strategies_to_run.append(f"Sharpe: {sharpe_per_symbol} комб.")
    if not test_strategy or test_strategy == 'skewness':
        strategies_to_run.append(f"Skewness: {skewness_per_symbol} комб.")
    if not test_strategy or test_strategy == 'bayesian':
        strategies_to_run.append(f"Bayesian: {bayesian_per_symbol} комб.")
    if not test_strategy or test_strategy == 'kurtosis':
        strategies_to_run.append(f"Kurtosis: {kurtosis_per_symbol} комб.")
    if not test_strategy or test_strategy == 'chi_square':
        strategies_to_run.append(f"ChiSq: {chi_square_per_symbol} комб.")

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

