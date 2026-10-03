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
from risk_manager import json_default


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
        return data.get('results', []), data.get('last_bar_time'), data.get('families')
    except (json.JSONDecodeError, KeyError):
        return None, None


def save_checkpoint(symbol, results, last_bar_time=None, families=None):
    """Сохранить результаты для символа в чекпойнт."""
    path = _checkpoint_file(symbol)
    data = {
        'symbol': symbol,
        'timestamp': datetime.datetime.now().isoformat(),
        'n_results': len(results),
        'last_bar_time': last_bar_time,
        'families': families,
        'results': results
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'), default=json_default)


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


def _backtest_vwap(df, vol_period, std_mult, sl_points, tp_points,
                   point, tick_value, tick_size, spread_points=0):
    """Backtest для VWAP Reversion."""
    from strategies.vwap_reversion import backtest as backtest_vwap
    return backtest_vwap(df, vol_period, std_mult, sl_points, tp_points, point,
                         tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_momentum(df, momentum_period, threshold, sl_points, tp_points,
                       point, tick_value, tick_size, spread_points=0):
    """Backtest для Momentum Breakout."""
    from strategies.momentum_breakout import backtest as backtest_momentum
    return backtest_momentum(df, momentum_period, threshold, sl_points, tp_points, point,
                             tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_pin_bar(df, body_ratio, sl_points, tp_points,
                      point, tick_value, tick_size, spread_points=0):
    """Backtest для Pin Bar Reversal."""
    from strategies.pin_bar_reversal import backtest as backtest_pin_bar
    return backtest_pin_bar(df, body_ratio, True, sl_points, tp_points, point,
                            tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_prev_daily(df, hold_bars, sl_points, tp_points,
                         point, tick_value, tick_size, spread_points=0):
    """Backtest для Prev Daily Candle Direction."""
    from strategies.prev_daily_candle_direction import backtest as backtest_prev_daily
    return backtest_prev_daily(df, hold_bars, sl_points, tp_points, point,
                               tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_corr(df, window, corr_threshold, sl_points, tp_points,
                   point, tick_value, tick_size, spread_points=0):
    """Backtest для Rolling Correlation Momentum."""
    from strategies.rolling_correlation_momentum import backtest as backtest_corr
    return backtest_corr(df, window, corr_threshold, sl_points, tp_points, point,
                         tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


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
            print(f'Попытка подключения: {accounts_credentials['demo'][0]}')
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
        balance = account_info.balance
        equity = account_info.equity
        msg = f'баланс: {balance:.2f} | equity: {equity:.2f}'
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



# ═══ БЭКТЕСТ ═══
class _FamilyFilter:
    """Псевдо-test_strategy для инкрементального пересчёта: == имя -> True,
    если семейство в разрешённом списке. Позволяет переиспользовать
    существующие guard'ы 'if not test_strategy or test_strategy == X' без
    правок каждого блока."""
    def __init__(self, names):
        self.names = set(names)

    def __eq__(self, other):
        return other in self.names

    def __bool__(self):
        return True

    def __repr__(self):
        return f"_FamilyFilter({sorted(self.names)})"


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


def _run_symbol_safe(args):
    """Безопасный запуск бэктеста одного символа: ошибка внутри него
    не роняет весь расчёт — воркер возвращает пустой результат."""
    try:
        return _backtest_symbol(args)
    except Exception as exc:
        symbol = args[1] if len(args) > 1 else '?'
        print(f"\n  [ERROR] Символ {symbol} не рассчитан: {exc!r} — пропускаем",
              flush=True)
        return symbol, [], 0, 0, []


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
     VWAP_VOL_PERIOD_LIST, VWAP_STD_MULT_LIST, MOMENTUM_PERIOD_LIST, MOMENTUM_THRESHOLD_LIST,
     PIN_BAR_BODY_RATIO_LIST, PREV_DAILY_HOLD_BARS_LIST, CORR_WINDOW_LIST, CORR_THRESHOLD_LIST,
     BACKTEST_DAYS, test_strategy, test_mode, total_symbols,

     family_fp, recalc_families) = args

    # Инкрементальный пересчёт: считаем только указанные семейства.
    if recalc_families is not None:
        test_strategy = _FamilyFilter(recalc_families)

    # Восстановить объект "info" из примитивного словаря
    info = _reconstruct_symbol_info(symbol, info_dict)

    from strategy_engine import calc_metrics, composite_score, deduplicate_results

    # ── Предрасчёт размеров (все 23 стратегии) ──
    stoch_per_symbol = len(K_PERIODS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    parab_per_symbol = len(PARABOLIC_STEPS) * len(PARABOLIC_MAXS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    ma_per_symbol = len(MA_PERIODS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    rf_per_symbol = len(RF_LOOKBACKS) * len(RF_NBARS) * len(RF_THRESHOLDS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    logreg_per_symbol = len(LOGREG_LOOKBACKS) * len(LOGREG_NBARS) * len(LOGREG_THRESHOLDS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
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
    zscore_per_symbol = len(ZSCORE_SMA_PERIOD_LIST) * len(ZSCORE_THRESHOLD_LIST) * len(ZSCORE_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    autocorr_per_symbol = len(AUTOCORR_LAG_LIST) * len(AUTOCORR_THRESHOLD_LIST) * len(AUTOCORR_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    hurst_per_symbol = len(HURST_WINDOW_LIST) * len(HURST_TREND_THRESHOLD_LIST) * len(HURST_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    lrc_per_symbol = len(LRC_PERIOD_LIST) * len(LRC_STD_THRESHOLD_LIST) * len(LRC_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    percentile_per_symbol = len(PCT_PERIOD_LIST) * len(PCT_LOW_LIST) * len(PCT_HIGH_LIST) * len(PCT_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    runs_per_symbol = len(RUNS_WINDOW_LIST) * len(RUNS_THRESHOLD_LIST) * len(RUNS_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    coint_per_symbol = len(COINT_WINDOW_LIST) * len(COINT_THRESHOLD_LIST) * len(COINT_BETA_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    sharpe_per_symbol = len(SHARPE_WINDOW_LIST) * len(SHARPE_THRESHOLD_LIST) * len(SHARPE_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    skewness_per_symbol = len(SKEW_WINDOW_LIST) * len(SKEW_THRESHOLD_LIST) * len(SKEW_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    bayesian_per_symbol = len(BAYES_WINDOW_LIST) * len(BAYES_THRESHOLD_LIST) * len(BAYES_PRIOR_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    kurtosis_per_symbol = len(KURT_WINDOW_LIST) * len(KURT_THRESHOLD_LIST) * len(KURT_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    chi_square_per_symbol = len(CHISQ_WINDOW_LIST) * len(CHISQ_ENTRY_LIST) * len(CHISQ_EXIT_LIST) * len(CHISQ_VOL_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    vwap_per_symbol = len(VWAP_VOL_PERIOD_LIST) * len(VWAP_STD_MULT_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    momentum_per_symbol = len(MOMENTUM_PERIOD_LIST) * len(MOMENTUM_THRESHOLD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    pin_bar_per_symbol = len(PIN_BAR_BODY_RATIO_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    prev_daily_per_symbol = len(PREV_DAILY_HOLD_BARS_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    corr_per_symbol = len(CORR_WINDOW_LIST) * len(CORR_THRESHOLD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)

    _strategy_map = {
        'stoch': stoch_per_symbol,
        'parabolic': parab_per_symbol,
        'ma': ma_per_symbol,
        'rf': rf_per_symbol,
        'logreg': logreg_per_symbol,
        'macd_cross': macd_cross_per_symbol,
        'rsi_rev': rsi_rev_per_symbol,
        'bollinger': bollinger_per_symbol,
        'ema_cross': ema_cross_per_symbol,
        'rsi_div': rsi_div_per_symbol,
        'ichimoku': ichimoku_per_symbol,
        'zscore': zscore_per_symbol,
        'autocorr': autocorr_per_symbol,
        'hurst': hurst_per_symbol,
        'lrc': lrc_per_symbol,
        'percentile': percentile_per_symbol,
        'runs': runs_per_symbol,
        'coint': coint_per_symbol,
        'sharpe': sharpe_per_symbol,
        'skewness': skewness_per_symbol,
        'bayesian': bayesian_per_symbol,
        'kurtosis': kurtosis_per_symbol,
        'chi_square': chi_square_per_symbol,
        'vwap': vwap_per_symbol,
        'momentum': momentum_per_symbol,
        'pin_bar': pin_bar_per_symbol,
        'prev_daily': prev_daily_per_symbol,
        'corr_momentum': corr_per_symbol,
    }

    if test_strategy in _strategy_map:
        active_combos = _strategy_map[test_strategy]
    else:
        active_combos = sum(_strategy_map.values())

    status = "старт" if symbol_idx < 4 else "в очереди"
    print(f"  [{symbol_idx + 1}/{total_symbols}] {symbol}: {status} ({active_combos} комб.)", flush=True)

    results = []
    combos_done = 0
    completed_strategies = []

    def _safe_backtest(strategy_name, bt_fn, *args, **kwargs):
        nonlocal combos_done
        try:
            return bt_fn(*args, **kwargs)
        except Exception as e:
            print(f"  [ERROR] {symbol} | {strategy_name}: {e}", flush=True)
            return 0, 0, []

    # ── Стохастик ──
    if not test_strategy or test_strategy == 'stoch':
        for k, sl, tp in product(K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST):
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
        for step, max_val, sl, tp in product(
            PARABOLIC_STEPS, PARABOLIC_MAXS, SL_POINTS_LIST, TP_POINTS_LIST
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
        for ma_period, sl, tp in product(MA_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST):
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
        for lookback, n_bars, threshold, sl, tp in product(
            RF_LOOKBACKS, RF_NBARS, RF_THRESHOLDS, SL_POINTS_LIST, TP_POINTS_LIST
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
        for lookback, n_bars, threshold, sl, tp in product(
            LOGREG_LOOKBACKS, LOGREG_NBARS, LOGREG_THRESHOLDS, SL_POINTS_LIST, TP_POINTS_LIST
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
        for mf, ms, msig, sl, tp in product(
            MACD_CROSS_FAST_LIST, MACD_CROSS_SLOW_LIST, MACD_CROSS_SIGNAL_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
        for rp, ros, rob, sl, tp in product(
            RSI_REV_PERIOD_LIST, RSI_REV_OVERSOLD_LIST, RSI_REV_OVERBOUGHT_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
        for bp, bs, vp, sl, tp in product(
            BB_PERIOD_LIST, BB_STD_LIST, VOLUME_PERIOD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
        for ef, es, sl, tp in product(
            EMA_FAST_LIST, EMA_SLOW_LIST, SL_POINTS_LIST, TP_POINTS_LIST
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
        for rp, lb, th, sl, tp in product(
            RSI_DIV_PERIOD_LIST, RSI_DIV_LOOKBACK_LIST, RSI_DIV_THRESHOLD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
        for ten, kij, senk, disp, sl, tp in product(
            TENKAN_LIST, KIJUN_LIST, SENKOU_B_LIST, DISPLACEMENT_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
        for sma_p, z_th, vol_p, sl, tp in product(
            ZSCORE_SMA_PERIOD_LIST, ZSCORE_THRESHOLD_LIST, ZSCORE_VOL_PERIOD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
                'param_key': f"sma{sma_p}_z{z_th:.1f}_v{vol_p}",
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
        for acf_lag, acf_th, vol_p, sl, tp in product(
            AUTOCORR_LAG_LIST, AUTOCORR_THRESHOLD_LIST, AUTOCORR_VOL_PERIOD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
                'param_key': f"lag{acf_lag}_th{acf_th:.2f}_v{vol_p}",
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
        for win, trend_th, vol_p, sl, tp in product(
            HURST_WINDOW_LIST, HURST_TREND_THRESHOLD_LIST, HURST_VOL_PERIOD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
                'param_key': f"win{win}_th{trend_th:.2f}_v{vol_p}",
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
        for period, std_th, vol_p, sl, tp in product(
            LRC_PERIOD_LIST, LRC_STD_THRESHOLD_LIST, LRC_VOL_PERIOD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
                'param_key': f"per{period}_std{std_th:.1f}_v{vol_p}",
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
        for per, pct_l, pct_h, vol_p, sl, tp in product(
            PCT_PERIOD_LIST, PCT_LOW_LIST, PCT_HIGH_LIST, PCT_VOL_PERIOD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
                'param_key': f"per{per}_l{pct_l}_h{pct_h}_v{vol_p}",
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
        for win, runs_th, vol_p, sl, tp in product(
            RUNS_WINDOW_LIST, RUNS_THRESHOLD_LIST, RUNS_VOL_PERIOD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
                'param_key': f"win{win}_th{runs_th:.1f}_v{vol_p}",
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
        for win, coint_th, beta_p, sl, tp in product(
            COINT_WINDOW_LIST, COINT_THRESHOLD_LIST, COINT_BETA_PERIOD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
                'param_key': f"win{win}_th{coint_th:.1f}_b{beta_p}",
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
        for win, sharpe_th, vol_p, sl, tp in product(
            SHARPE_WINDOW_LIST, SHARPE_THRESHOLD_LIST, SHARPE_VOL_PERIOD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
                'param_key': f"win{win}_th{sharpe_th:.2f}_v{vol_p}",
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
        for win, skew_th, vol_p, sl, tp in product(
            SKEW_WINDOW_LIST, SKEW_THRESHOLD_LIST, SKEW_VOL_PERIOD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
                'param_key': f"win{win}_th{skew_th:.1f}_v{vol_p}",
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
        for win, bay_th, prior, sl, tp in product(
            BAYES_WINDOW_LIST, BAYES_THRESHOLD_LIST, BAYES_PRIOR_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
                'param_key': f"win{win}_p{prior:.2f}_th{bay_th:.2f}",
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
        for win, kurt_th, vol_p, sl, tp in product(
            KURT_WINDOW_LIST, KURT_THRESHOLD_LIST, KURT_VOL_PERIOD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
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
                'param_key': f"win{win}_th{kurt_th:.1f}_v{vol_p}",
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
        for win, entry_th, exit_th, vol_p, sl, tp in product(
            CHISQ_WINDOW_LIST, CHISQ_ENTRY_LIST, CHISQ_EXIT_LIST, CHISQ_VOL_PERIOD_LIST,
     
     
            SL_POINTS_LIST, TP_POINTS_LIST
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
                'param_key': f"win{win}_e{entry_th:.2f}_x{exit_th:.2f}_v{vol_p}",
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

    # ── VWAP Reversion ──
    if not test_strategy or test_strategy == 'vwap':
        for vol_p, std_m, sl, tp in product(
            VWAP_VOL_PERIOD_LIST, VWAP_STD_MULT_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('VWAP', _backtest_vwap,
                df_window, vol_p, std_m, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'vwap',
                'param_key': f"vol{vol_p}_std{std_m:.1f}",
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
        completed_strategies.append('VWAP')

    # ── Momentum Breakout ──
    if not test_strategy or test_strategy == 'momentum':
        for per, mom_th, sl, tp in product(
            MOMENTUM_PERIOD_LIST, MOMENTUM_THRESHOLD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('Momentum', _backtest_momentum,
                df_window, per, mom_th, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'momentum',
                'param_key': f"per{per}_th{mom_th:.2f}",
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
        completed_strategies.append('Momentum')

    # ── Pin Bar Reversal ──
    if not test_strategy or test_strategy == 'pin_bar':
        for br, sl, tp in product(
            PIN_BAR_BODY_RATIO_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('PinBar', _backtest_pin_bar,
                df_window, br, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'pin_bar',
                'param_key': f"br{br:.1f}",
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
        completed_strategies.append('PinBar')

    # ── Prev Daily Candle Direction ──
    if not test_strategy or test_strategy == 'prev_daily':
        for hb, sl, tp in product(
            PREV_DAILY_HOLD_BARS_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('PrevDaily', _backtest_prev_daily,
                df_window, hb, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'prev_daily',
                'param_key': f"hb{hb}",
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
        completed_strategies.append('PrevDaily')

    # ── Rolling Correlation Momentum ──
    if not test_strategy or test_strategy == 'corr_momentum':
        for win, corr_th, sl, tp in product(
            CORR_WINDOW_LIST, CORR_THRESHOLD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('CorrMomentum', _backtest_corr,
                df_window, win, corr_th, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'corr_momentum',
                'param_key': f"win{win}_th{corr_th:.1f}",
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
        completed_strategies.append('CorrMomentum')

    # ── Сохраняем чекпойнт после каждого символа ──
    last_bar_time = df_window.index[-1].isoformat() if df_window is not None else None
    save_checkpoint(symbol, results, last_bar_time=last_bar_time, families=family_fp)

    return symbol, results, combos_done, active_combos, completed_strategies



def run_full_backtest(symbols, symbol_data, strategy_params, backtest_config,
                      test_strategy=None, test_mode=False, force_recalc=False,
                      incremental=False, is_night_run=True):
    """Перебирает все комбинации стратегий. Возвращает (top, all_results).

    TOP_N — максимальное число стратегий на ОДНУ валюту.
    test_strategy — если задан, тестирует только одну стратегию.
    test_mode — если True, выводит спец-сообщение для тестового режима.
    force_recalc — если True, игнорирует чекпойнты и пересчитывает всё с нуля.
    is_night_run — если True, это ночной прогон: полный пересчёт + запись night_reset.json.
    """

    # ── Ночное окно: старт прогона между 00:00 и 04:00 ──
    NIGHT_WINDOW_START = 0
    NIGHT_WINDOW_END = 4

    # ── Распаковка контейнеров ──
    SYMBOLS = list(symbols)
    K_PERIODS = strategy_params.k_periods
    SL_POINTS_LIST = strategy_params.sl_points_list
    TP_POINTS_LIST = strategy_params.tp_points_list
    PARABOLIC_STEPS = strategy_params.parabolic_steps
    PARABOLIC_MAXS = strategy_params.parabolic_maxs
    MA_PERIODS = strategy_params.ma_periods
    RF_LOOKBACKS = strategy_params.rf_lookbacks
    RF_NBARS = strategy_params.rf_nbars
    RF_THRESHOLDS = strategy_params.rf_thresholds
    LOGREG_LOOKBACKS = strategy_params.logreg_lookbacks
    LOGREG_NBARS = strategy_params.logreg_nbars
    LOGREG_THRESHOLDS = strategy_params.logreg_thresholds
    MACD_CROSS_FAST_LIST = strategy_params.macd_cross_fast_list
    MACD_CROSS_SLOW_LIST = strategy_params.macd_cross_slow_list
    MACD_CROSS_SIGNAL_LIST = strategy_params.macd_cross_signal_list
    RSI_REV_PERIOD_LIST = strategy_params.rsi_rev_period_list
    RSI_REV_OVERSOLD_LIST = strategy_params.rsi_rev_oversold_list
    RSI_REV_OVERBOUGHT_LIST = strategy_params.rsi_rev_overbought_list
    BB_PERIOD_LIST = strategy_params.bb_period_list
    BB_STD_LIST = strategy_params.bb_std_list
    VOLUME_PERIOD_LIST = strategy_params.volume_period_list
    EMA_FAST_LIST = strategy_params.ema_fast_list
    EMA_SLOW_LIST = strategy_params.ema_slow_list
    RSI_DIV_PERIOD_LIST = strategy_params.rsi_div_period_list
    RSI_DIV_LOOKBACK_LIST = strategy_params.rsi_div_lookback_list
    RSI_DIV_THRESHOLD_LIST = strategy_params.rsi_div_threshold_list
    TENKAN_LIST = strategy_params.tenkan_list
    KIJUN_LIST = strategy_params.kijun_list
    SENKOU_B_LIST = strategy_params.senkou_b_list
    DISPLACEMENT_LIST = strategy_params.displacement_list
    ZSCORE_SMA_PERIOD_LIST = strategy_params.zscore_sma_period_list
    ZSCORE_THRESHOLD_LIST = strategy_params.zscore_threshold_list
    ZSCORE_VOL_PERIOD_LIST = strategy_params.zscore_vol_period_list
    AUTOCORR_LAG_LIST = strategy_params.autocorr_lag_list
    AUTOCORR_THRESHOLD_LIST = strategy_params.autocorr_threshold_list
    AUTOCORR_VOL_PERIOD_LIST = strategy_params.autocorr_vol_period_list
    HURST_WINDOW_LIST = strategy_params.hurst_window_list
    HURST_TREND_THRESHOLD_LIST = strategy_params.hurst_trend_threshold_list
    HURST_VOL_PERIOD_LIST = strategy_params.hurst_vol_period_list
    LRC_PERIOD_LIST = strategy_params.lrc_period_list
    LRC_STD_THRESHOLD_LIST = strategy_params.lrc_std_threshold_list
    LRC_VOL_PERIOD_LIST = strategy_params.lrc_vol_period_list
    PCT_PERIOD_LIST = strategy_params.pct_period_list
    PCT_LOW_LIST = strategy_params.pct_low_list
    PCT_HIGH_LIST = strategy_params.pct_high_list
    PCT_VOL_PERIOD_LIST = strategy_params.pct_vol_period_list
    RUNS_WINDOW_LIST = strategy_params.runs_window_list
    RUNS_THRESHOLD_LIST = strategy_params.runs_threshold_list
    RUNS_VOL_PERIOD_LIST = strategy_params.runs_vol_period_list
    COINT_WINDOW_LIST = strategy_params.coint_window_list
    COINT_THRESHOLD_LIST = strategy_params.coint_threshold_list
    COINT_BETA_PERIOD_LIST = strategy_params.coint_beta_period_list
    SHARPE_WINDOW_LIST = strategy_params.sharpe_window_list
    SHARPE_THRESHOLD_LIST = strategy_params.sharpe_threshold_list
    SHARPE_VOL_PERIOD_LIST = strategy_params.sharpe_vol_period_list
    SKEW_WINDOW_LIST = strategy_params.skew_window_list
    SKEW_THRESHOLD_LIST = strategy_params.skew_threshold_list
    SKEW_VOL_PERIOD_LIST = strategy_params.skew_vol_period_list
    BAYES_WINDOW_LIST = strategy_params.bayes_window_list
    BAYES_THRESHOLD_LIST = strategy_params.bayes_threshold_list
    BAYES_PRIOR_LIST = strategy_params.bayes_prior_list
    KURT_WINDOW_LIST = strategy_params.kurt_window_list
    KURT_THRESHOLD_LIST = strategy_params.kurt_threshold_list
    KURT_VOL_PERIOD_LIST = strategy_params.kurt_vol_period_list
    CHISQ_WINDOW_LIST = strategy_params.chisq_window_list
    CHISQ_ENTRY_LIST = strategy_params.chisq_entry_list
    CHISQ_EXIT_LIST = strategy_params.chisq_exit_list
    CHISQ_VOL_PERIOD_LIST = strategy_params.chisq_vol_period_list
    VWAP_VOL_PERIOD_LIST = strategy_params.vwap_vol_period_list
    VWAP_STD_MULT_LIST = strategy_params.vwap_std_mult_list
    MOMENTUM_PERIOD_LIST = strategy_params.momentum_period_list
    MOMENTUM_THRESHOLD_LIST = strategy_params.momentum_threshold_list
    PIN_BAR_BODY_RATIO_LIST = strategy_params.pin_bar_body_ratio_list
    PREV_DAILY_HOLD_BARS_LIST = strategy_params.prev_daily_hold_bars_list
    CORR_WINDOW_LIST = strategy_params.corr_window_list
    CORR_THRESHOLD_LIST = strategy_params.corr_threshold_list
    BACKTEST_DAYS = backtest_config.backtest_days
    TOP_N = backtest_config.top_n

    from strategy_engine import calc_metrics, composite_score, deduplicate_results

    all_results = []
    global_start = time.time()

    # ── Статистика прошлого прогона ──
    last_run_path = os.path.join(_checkpoint_dir(), 'last_run.json')
    last_run = None
    if os.path.exists(last_run_path):
        try:
            with open(last_run_path, 'r', encoding='utf-8') as f:
                last_run = json.load(f)
        except (json.JSONDecodeError, OSError):
            last_run = None

    # ── Предрасчёт размеров комбинаций на 1 символ ──
    stoch_per_symbol = len(K_PERIODS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    parab_per_symbol = len(PARABOLIC_STEPS) * len(PARABOLIC_MAXS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    ma_per_symbol = len(MA_PERIODS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    rf_per_symbol = len(RF_LOOKBACKS) * len(RF_NBARS) * len(RF_THRESHOLDS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    logreg_per_symbol = len(LOGREG_LOOKBACKS) * len(LOGREG_NBARS) * len(LOGREG_THRESHOLDS) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)

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
    vwap_per_symbol = (len(VWAP_VOL_PERIOD_LIST) * len(VWAP_STD_MULT_LIST) *
                       len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    momentum_per_symbol = (len(MOMENTUM_PERIOD_LIST) * len(MOMENTUM_THRESHOLD_LIST) *
                           len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    pin_bar_per_symbol = (len(PIN_BAR_BODY_RATIO_LIST) *
                          len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    prev_daily_per_symbol = (len(PREV_DAILY_HOLD_BARS_LIST) *
                             len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    corr_per_symbol = (len(CORR_WINDOW_LIST) * len(CORR_THRESHOLD_LIST) *
                       len(SL_POINTS_LIST) * len(TP_POINTS_LIST))

    # ── Карта: test_strategy → кол-во комбинаций ──
    strat_combo_map = {
        'stoch': stoch_per_symbol,
        'parabolic': parab_per_symbol,
        'ma': ma_per_symbol,
        'rf': rf_per_symbol,
        'logreg': logreg_per_symbol,
        'macd_cross': macd_cross_per_symbol,
        'rsi_rev': rsi_rev_per_symbol,
        'bollinger': bollinger_per_symbol,
        'ema_cross': ema_cross_per_symbol,
        'rsi_div': rsi_div_per_symbol,
        'ichimoku': ichimoku_per_symbol,
        'zscore': zscore_per_symbol,
        'autocorr': autocorr_per_symbol,
        'hurst': hurst_per_symbol,
        'lrc': lrc_per_symbol,
        'percentile': percentile_per_symbol,
        'runs': runs_per_symbol,
        'coint': coint_per_symbol,
        'sharpe': sharpe_per_symbol,
        'skewness': skewness_per_symbol,
        'bayesian': bayesian_per_symbol,
        'kurtosis': kurtosis_per_symbol,
        'chi_square': chi_square_per_symbol,
        'vwap': vwap_per_symbol,
        'momentum': momentum_per_symbol,
        'pin_bar': pin_bar_per_symbol,
        'prev_daily': prev_daily_per_symbol,
        'corr_momentum': corr_per_symbol,
    }

    if test_strategy and test_strategy in strat_combo_map:
        active_combos = strat_combo_map[test_strategy]
    else:
        active_combos = sum(strat_combo_map.values())

    combos_per_symbol = active_combos

    # ── Отпечатки семейств для инкрементального пересчёта ──
    def _fp(*lsts):
        return tuple(tuple(l) for l in lsts)

    family_fp = {
        'stoch': _fp(K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST),
        'parabolic': _fp(PARABOLIC_STEPS, PARABOLIC_MAXS, SL_POINTS_LIST, TP_POINTS_LIST),
        'ma': _fp(MA_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST),
        'rf': _fp(RF_LOOKBACKS, RF_NBARS, RF_THRESHOLDS, SL_POINTS_LIST, TP_POINTS_LIST),
        'logreg': _fp(LOGREG_LOOKBACKS, LOGREG_NBARS, LOGREG_THRESHOLDS, SL_POINTS_LIST, TP_POINTS_LIST),
        'macd_cross': _fp(MACD_CROSS_FAST_LIST, MACD_CROSS_SLOW_LIST, MACD_CROSS_SIGNAL_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'rsi_rev': _fp(RSI_REV_PERIOD_LIST, RSI_REV_OVERSOLD_LIST, RSI_REV_OVERBOUGHT_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'bollinger': _fp(BB_PERIOD_LIST, BB_STD_LIST, VOLUME_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'ema_cross': _fp(EMA_FAST_LIST, EMA_SLOW_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'rsi_div': _fp(RSI_DIV_PERIOD_LIST, RSI_DIV_LOOKBACK_LIST, RSI_DIV_THRESHOLD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'ichimoku': _fp(TENKAN_LIST, KIJUN_LIST, SENKOU_B_LIST, DISPLACEMENT_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'zscore': _fp(ZSCORE_SMA_PERIOD_LIST, ZSCORE_THRESHOLD_LIST, ZSCORE_VOL_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'autocorr': _fp(AUTOCORR_LAG_LIST, AUTOCORR_THRESHOLD_LIST, AUTOCORR_VOL_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'hurst': _fp(HURST_WINDOW_LIST, HURST_TREND_THRESHOLD_LIST, HURST_VOL_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'lrc': _fp(LRC_PERIOD_LIST, LRC_STD_THRESHOLD_LIST, LRC_VOL_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'percentile': _fp(PCT_PERIOD_LIST, PCT_LOW_LIST, PCT_HIGH_LIST, PCT_VOL_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'runs': _fp(RUNS_WINDOW_LIST, RUNS_THRESHOLD_LIST, RUNS_VOL_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'coint': _fp(COINT_WINDOW_LIST, COINT_THRESHOLD_LIST, COINT_BETA_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'sharpe': _fp(SHARPE_WINDOW_LIST, SHARPE_THRESHOLD_LIST, SHARPE_VOL_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'skewness': _fp(SKEW_WINDOW_LIST, SKEW_THRESHOLD_LIST, SKEW_VOL_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'bayesian': _fp(BAYES_WINDOW_LIST, BAYES_THRESHOLD_LIST, BAYES_PRIOR_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'kurtosis': _fp(KURT_WINDOW_LIST, KURT_THRESHOLD_LIST, KURT_VOL_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'chi_square': _fp(CHISQ_WINDOW_LIST, CHISQ_ENTRY_LIST, CHISQ_EXIT_LIST, CHISQ_VOL_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'vwap': _fp(VWAP_VOL_PERIOD_LIST, VWAP_STD_MULT_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'momentum': _fp(MOMENTUM_PERIOD_LIST, MOMENTUM_THRESHOLD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'pin_bar': _fp(PIN_BAR_BODY_RATIO_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'prev_daily': _fp(PREV_DAILY_HOLD_BARS_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'corr_momentum': _fp(CORR_WINDOW_LIST, CORR_THRESHOLD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
    }

    # ═══ ПРОВЕРКА НОЧНОГО ПЕРЕСЧЁТА ═══
    now = datetime.datetime.now()
    last_night_reset = None
    night_reset_path = os.path.join(_checkpoint_dir(), 'night_reset.json')

    if os.path.exists(night_reset_path):
        try:
            with open(night_reset_path, 'r', encoding='utf-8') as f:
                night_data = json.load(f)
            last_night_reset = datetime.datetime.fromisoformat(night_data.get('timestamp', ''))
        except (json.JSONDecodeError, ValueError, OSError):
            last_night_reset = None


    # Ночной прогон или force_recalc — всегда полный пересчёт.
    # Иначе: есть night_reset.json — используем чекпоинты, пересчёт не нужен.
    # Нет night_reset.json — первый запуск, полный пересчёт.
    # 
    # ЛОГИКА:
    # force_recalc=True  → лайт в будни (force_full_recalc=False), полный на выходных (force_full_recalc=True)
    # force_recalc=False → полный пересчёт НЕ ЗАПУСКАЕТСЯ НИКОГДА (только лайт-пересчёты в 3:00)
    if not force_recalc:
        # force_recalc=False — полный пересчёт отключён, только лайт
        force_full_recalc = False
    elif is_night_run:
        # force_recalc=True + ночной прогон → полный пересчёт
        force_full_recalc = True
    else:
        # Не ночной прогон — проверяем night_reset
        force_full_recalc = last_night_reset is None

    # ═══ МАРКЕР СТАРТА НОЧНОГО ПРОГОНА ═══
    # Пишем сразу, чтобы даже при падении night_reset.json фиксирует факт запуска
    if is_night_run:
        try:
            with open(night_reset_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': now.isoformat(),
                    'status': 'started',
                    'symbols': len(SYMBOLS),
                }, f, ensure_ascii=False, indent=2)
            print(f"\n  🌙 Ночной прогон стартовал: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        except (OSError, TypeError):
            pass

    if force_full_recalc:
        if is_night_run:
            print(f"\n  🌙 Ночной прогон — полный пересчёт всех стратегий")
        elif force_recalc:
            print(f"\n  ⚡ Принудительный пересчёт — чекпойнты игнорируются")
        else:
            print(f"\n  🌙 Ночного пересчёта сегодня ещё не было — считаем ВСЕ стратегии заново")
    else:
        if last_night_reset:
            print(f"\n  ✅ Ночной пересчёт выполнен {last_night_reset.strftime('%H:%M')} — кэш + инкремент новых стратегий")
        else:
            print(f"\n  🌙 Нет night_reset.json — считаем ВСЕ стратегии заново")

    # ═══ ЗАГРУЗКА ЧЕКПОЙНТОВ ═══
    existing_checkpoints = list_checkpoints()
    skipped_symbols = {}
    partial_recalc = {}
    reuse_stale = []
    cached_results = []

    for symbol in SYMBOLS:
        if force_full_recalc:
            continue
        if symbol not in existing_checkpoints:
            continue
        if symbol not in symbol_data:
            continue

        cached, cached_bar_time, cached_families = load_checkpoint(symbol)
        if cached is None:
            continue


        df = symbol_data[symbol]['df_h1']
        current_bar_time = df.index[-1].isoformat()

        cached_fams = cached_families or {}

        if cached_fams:
            cached_fams = {
                k: tuple(tuple(x) for x in v) if isinstance(v, list) else v
                for k, v in cached_fams.items()
            }
            missing_families = [f for f in family_fp if f not in cached_fams]
            changed_families = [
                f for f, fp in family_fp.items()
                if f in cached_fams and cached_fams.get(f) != fp
            ]
            recalc_set = set(missing_families + changed_families)
        else:
            recalc_set = set()

        if cached_bar_time == current_bar_time:
            # Данные не изменились с ночного пересчёта
            if not recalc_set:
                # Конфиг тот же, данные те же — кэш полностью валиден
                cached_results.extend(cached)
                skipped_symbols[symbol] = len(cached)
            else:
                # Данные те же, но конфиг изменился — частичный пересчёт
                partial_recalc[symbol] = (cached, recalc_set)
        else:
            # Данные изменились после ночного пересчёта
            if not recalc_set:
                # Конфиг не менялся — переиспользуем кэш (инкремент для новых баров)
                cached_results.extend(cached)
                skipped_symbols[symbol] = len(cached)
                reuse_stale.append(symbol)
            else:
                # Конфиг изменился + данные изменились — частичный пересчёт
                partial_recalc[symbol] = (cached, recalc_set)

    # ── Вывод статуса чекпойнтов (компактный) ──
    actions_summary = []

    if force_recalc and not is_night_run:
        actions_summary.append("⚡ Принудительный пересчёт — чекпойнты игнорируются")

    if not force_full_recalc and not existing_checkpoints:
        actions_summary.append("ℹ Чекпойнтов нет — будет полный пересчёт")

    if partial_recalc:
        count = len(partial_recalc)
        actions_summary.append(f"🔄 Частичный пересчёт: {count} символа(ов) с изменёнными семействами")
        # Если хочешь видеть детали только когда их мало (например, ≤3), иначе — тишина
        if count <= 3:
            for sym, (_, recalc_set) in partial_recalc.items():
                actions_summary.append(f"   • {sym}: {', '.join(sorted(recalc_set))}")

    if skipped_symbols and not partial_recalc:
        # Только если всё из кэша и ничего не пересчитываем
        total_results = sum(skipped_symbols.values())
        actions_summary.append(
            f"📦 Кэш валиден: {len(skipped_symbols)} символов, {total_results:,} результатов (пересчёт не нужен)"
        )

    # Вывод: либо список действий, либо тишина (если всё ок и без шума)
    if actions_summary:
        print()
        for line in actions_summary:
            print(line)
    else:
        # Опционально: если вообще ничего не печатаем — можно дать одну нейтральную строку
        # print("✅ Чекпойнты валидны, пересчёт не требуется")
        pass

    # ── Сбор valid_symbols ──
    valid_symbols = []
    for symbol in SYMBOLS:
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

    # ── Сбор аргументов для каждого символа ──
    symbol_args = []
    for idx, symbol in enumerate(valid_symbols):
        sd = symbol_data[symbol]
        if sd.get('df_h1') is None or sd.get('info') is None:
            print(f"  ⚠ {symbol}: нет данных (df_h1/info) — пропускаем, расчёт продолжается", flush=True)
            continue
        info = sd['info']
        info_dict = {
            'point': getattr(info, 'point', None) or 0,
            'trade_tick_value': getattr(info, 'trade_tick_value', None) or getattr(info, 'tick_value', None) or 0,
            'trade_tick_size': getattr(info, 'trade_tick_size', None) or getattr(info, 'tick_size', None) or 0,
            'spread': getattr(info, 'spread', None) or 0,
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
            VWAP_VOL_PERIOD_LIST, VWAP_STD_MULT_LIST, MOMENTUM_PERIOD_LIST, MOMENTUM_THRESHOLD_LIST,
            PIN_BAR_BODY_RATIO_LIST, PREV_DAILY_HOLD_BARS_LIST, CORR_WINDOW_LIST, CORR_THRESHOLD_LIST,


            BACKTEST_DAYS, test_strategy, test_mode, total_symbols,
            family_fp, partial_recalc.get(symbol, (None, None))[1]
        ))

    total_combos = combos_per_symbol * total_symbols
    n_skipped = len(skipped_symbols)

    # ── Вывод плана бэктеста ──
    print(f"\n{'═' * 60}")
    if n_skipped > 0:
        print(f"  БЭКТЕСТ | {total_symbols} символов × {combos_per_symbol} комб. = {total_combos} всего")
        print(f"  ⏭ Пропущено расчетов после загрузки чекпойнтов: {n_skipped} символов")
    else:
        print(f"  БЭКТЕСТ | {total_symbols} символов × {combos_per_symbol} комб. = {total_combos} всего")
    print(f"{'═' * 60}")

    # ── Какие стратегии считаются ──
    strategies_to_run = []
    if not test_strategy or test_strategy == 'stoch':
        strategies_to_run.append(("Stoch", stoch_per_symbol))
    if not test_strategy or test_strategy == 'parabolic':
        strategies_to_run.append(("Parabolic", parab_per_symbol))
    if not test_strategy or test_strategy == 'ma':
        strategies_to_run.append(("MA", ma_per_symbol))
    if not test_strategy or test_strategy == 'rf':
        strategies_to_run.append(("RF", rf_per_symbol))
    if not test_strategy or test_strategy == 'logreg':
        strategies_to_run.append(("LogReg", logreg_per_symbol))
    if not test_strategy or test_strategy == 'bollinger':
        strategies_to_run.append(("Bollinger", bollinger_per_symbol))
    if not test_strategy or test_strategy == 'ema_cross':
        strategies_to_run.append(("EMA", ema_cross_per_symbol))
    if not test_strategy or test_strategy == 'rsi_div':
        strategies_to_run.append(("RSI-Div", rsi_div_per_symbol))
    if not test_strategy or test_strategy == 'ichimoku':
        strategies_to_run.append(("Ichimoku", ichimoku_per_symbol))
    if not test_strategy or test_strategy == 'macd_cross':
        strategies_to_run.append(("MACD-Cross", macd_cross_per_symbol))
    if not test_strategy or test_strategy == 'rsi_rev':
        strategies_to_run.append(("RSI-Rev", rsi_rev_per_symbol))
    if not test_strategy or test_strategy == 'zscore':
        strategies_to_run.append(("Zscore", zscore_per_symbol))
    if not test_strategy or test_strategy == 'autocorr':
        strategies_to_run.append(("Autocorr", autocorr_per_symbol))
    if not test_strategy or test_strategy == 'hurst':
        strategies_to_run.append(("Hurst", hurst_per_symbol))
    if not test_strategy or test_strategy == 'lrc':
        strategies_to_run.append(("LRC", lrc_per_symbol))
    if not test_strategy or test_strategy == 'percentile':
        strategies_to_run.append(("Percentile", percentile_per_symbol))
    if not test_strategy or test_strategy == 'runs':
        strategies_to_run.append(("Runs", runs_per_symbol))
    if not test_strategy or test_strategy == 'coint':
        strategies_to_run.append(("Coint", coint_per_symbol))
    if not test_strategy or test_strategy == 'sharpe':
        strategies_to_run.append(("Sharpe", sharpe_per_symbol))
    if not test_strategy or test_strategy == 'skewness':
        strategies_to_run.append(("Skewness", skewness_per_symbol))
    if not test_strategy or test_strategy == 'bayesian':
        strategies_to_run.append(("Bayesian", bayesian_per_symbol))
    if not test_strategy or test_strategy == 'kurtosis':
        strategies_to_run.append(("Kurtosis", kurtosis_per_symbol))
    if not test_strategy or test_strategy == 'chi_square':
        strategies_to_run.append(("ChiSq", chi_square_per_symbol))
    if not test_strategy or test_strategy == 'vwap':
        strategies_to_run.append(("VWAP", vwap_per_symbol))
    if not test_strategy or test_strategy == 'momentum':
        strategies_to_run.append(("Momentum", momentum_per_symbol))
    if not test_strategy or test_strategy == 'pin_bar':
        strategies_to_run.append(("PinBar", pin_bar_per_symbol))
    if not test_strategy or test_strategy == 'prev_daily':
        strategies_to_run.append(("PrevDaily", prev_daily_per_symbol))
    if not test_strategy or test_strategy == 'corr_momentum':
        strategies_to_run.append(("CorrMomentum", corr_per_symbol))

    print("  Стратегии на 1 символ:")
    for name, count in sorted(strategies_to_run, key=lambda x: x[1], reverse=True):
        print(f"    {name}: {count} комб.")

    if test_strategy:
        print(f"  ⚡ Только: '{test_strategy}'")
    elif test_mode:
        print(f"  ⚡ Тестовый режим (минимальный перебор)")

    print(f"\n  Символы ({total_symbols}): {', '.join(valid_symbols)}")
    print(f"  Окно данных: {BACKTEST_DAYS} дн. × 24 ч = {BACKTEST_DAYS * 24} баров")
    if total_combos > 0:
        if last_run and last_run.get('combos') and last_run.get('elapsed_sec'):
            est_sec = max(1, int(last_run['elapsed_sec'] * (total_combos / max(1, last_run['combos']))))
            est_note = f"по прошлому прогону ({last_run['elapsed_sec']:.0f}с на {last_run['combos']} комб.)"
        else:
            est_sec = max(1, int(total_combos / (4 * 30)))
            est_note = "грубая оценка: ~30 комбинаций в секунду на 1 процесс, всего 4 процесса"
        print(f"  ⏱  Ориентировочно расчёт займёт ~{est_sec / 60:.0f} минут. {est_note}")
    elif total_symbols == 0:
        print(f"  ✅ Всё готово из чекпойнтов — расчёт не нужен")
    print(f"{'═' * 60}")

    # ── Запуск бэктеста ──
    n_processes = min(4, max(1, os.cpu_count() or 1))
    use_multiprocessing = len(symbol_args) > 1

    results_list = []
    done = 0

    if use_multiprocessing:
        print(f"\n  Multiprocessing: {n_processes} процессов\n")
        import multiprocessing as mp
        with mp.Pool(processes=n_processes) as pool:
            for item in pool.imap_unordered(_run_symbol_safe, symbol_args):
                results_list.append(item)
                done += 1
                symbol_done, results, combos_done, active_c, strats = item
                elapsed = time.time() - global_start
                eta_min = (total_symbols - done) * elapsed / max(done, 1) / 60
                print(f"\n  ✓ [{done}/{total_symbols}] {symbol_done} готово "
                      f"({combos_done} комб., {elapsed:.0f}с с начала) "
                      f"⏳ {done / total_symbols * 100:.0f}% | ETA ~{eta_min:.1f} мин")
                for strat_name in strats:
                    print(f"    {symbol_done} | {strat_name} ✓")
    else:
        print(f"\n  На пересчет пойдет: {total_symbols} символов\n")
        for args in symbol_args:
            item = _run_symbol_safe(args)
            results_list.append(item)
            done += 1
            symbol_done, results, combos_done, active_c, strats = item
            elapsed = time.time() - global_start
            eta_min = (total_symbols - done) * elapsed / max(done, 1) / 60
            print(f"\n  ✓ [{done}/{total_symbols}] {symbol_done} готово "
                  f"({combos_done} комб., {elapsed:.0f}с с начала) "
                  f"⏳ {done / total_symbols * 100:.0f}% | ETA ~{eta_min:.1f} мин")
            for strat_name in strats:
                print(f"    {symbol_done} | {strat_name} ✓")

    # ── Сбор результатов ──
    all_results = list(cached_results)   # ← начинаем с кэша пропущенных
    new_by_symbol = {}
    for item in results_list:
        symbol, results, combos_done, active_combos, completed_strategies = item
        new_by_symbol.setdefault(symbol, []).extend(results)

    # ── Мерж частичного пересчёта ──
    for symbol, (cached, recalc_set) in partial_recalc.items():
        kept = [r for r in cached
                if r.get('type') not in recalc_set and r.get('type') in family_fp]
        merged = kept + new_by_symbol.get(symbol, [])
        all_results.extend(merged)
        try:
            save_checkpoint(symbol, merged,
                            last_bar_time=symbol_data[symbol]['df_h1'].index[-1].isoformat(),
                            families=family_fp)
        except (OSError, TypeError):
            pass

    for symbol in new_by_symbol:
        if symbol not in partial_recalc:
            all_results.extend(new_by_symbol[symbol])

    total_elapsed = time.time() - global_start
    print(f"\n{'─' * 60}")
    print(f"  Всего посчитанных комбинаций из кэша или заново: {len(all_results)}")
    print(f"  ⏱  Бэктест завершён за {total_elapsed:.0f}с ({total_elapsed / 60:.1f} мин)")

    # ── Дедупликация и сортировка ──
    print(f"\n  Дедупликация {len(all_results)} результатов...")
    all_results = deduplicate_results(all_results)
    all_results.sort(key=lambda x: x['score'], reverse=True)

    # ── Топ-N стратегий на каждую валюту ──
    top_results = []
    for symbol in SYMBOLS:
        symbol_strats = [r for r in all_results if r['symbol'] == symbol]
        top_results.extend(symbol_strats[:TOP_N])

    print(f"  Активных стратегий: {len(top_results)}")
    print(f"{'─' * 60}\n")

    # ── Сохранение чекпойнтов для свежесчитанных символов ──
    for symbol in new_by_symbol:
        if symbol not in partial_recalc:
            try:
                save_checkpoint(symbol, new_by_symbol[symbol],
                                last_bar_time=symbol_data[symbol]['df_h1'].index[-1].isoformat(),
                                families=family_fp)
            except (OSError, TypeError):
                pass

    # ── Статистика прогона ──
    try:
        with open(last_run_path, 'w', encoding='utf-8') as f:
            json.dump({
                'combos': total_combos,
                'symbols': total_symbols,
                'elapsed_sec': round(total_elapsed, 1),
                'finished_at': datetime.datetime.now().isoformat(),
                'skipped_from_checkpoint': len(skipped_symbols),
                'is_night_run': is_night_run,
            }, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError):
        pass

    # ═══ ОБНОВЛЕНИЕ night_reset.json (статус completed) ═══
    if is_night_run:
        try:
            with open(night_reset_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': now.isoformat(),
                    'status': 'completed',
                    'symbols': total_symbols,
                    'total_results': len(all_results),
                    'elapsed_sec': round(total_elapsed, 1),
                }, f, ensure_ascii=False, indent=2)
            print(f"\n  🌙 Ночной пересчёт завершён: {total_symbols} символов, {len(all_results)} стратегий")
            print(f"  📅 Timestamp: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        except (OSError, TypeError):
            pass

    return top_results, all_results

