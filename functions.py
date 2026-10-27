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
class _safe_marker_write:
    """Контекст-менеджер вместо `with open(...) as f:` для JSON-маркеров.

    Зачем: записи ночных маркеров (night_reset.json, last_run.json) обёрнуты в
    `except (OSError, TypeError): pass`. При отказе диска или сетевой шары запись
    исчезала молча, и решение о следующем ПОЛНОМ пересчёте принималось по
    устаревшему маркеру без единой строки в логе. Здесь ошибка печатается, тело
    блока (json.dump) не меняется, а прогон не падает.
    """

    def __init__(self, path, label):
        self.path = path
        self.label = label
        self._file = None

    def __enter__(self):
        try:
            self._file = open(self.path, 'w', encoding='utf-8')
        except OSError as exc:
            # Открыть не удалось — пишем в никуда, но говорим об этом вслух.
            print(f"  [WARN] {self.label} не записан ({self.path}): {exc!r}", flush=True)
            import io
            return io.StringIO()
        return self._file

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._file is not None:
                self._file.close()
        except OSError:
            pass
        if exc_type is not None:
            print(f"  [WARN] {self.label} не записан ({self.path}): {exc!r}", flush=True)
            return True   # гасим: маркер не должен ронять прогон
        return False


def _history_path():
    """Путь к журналу прогонов бэктеста (JSONL, для вкладки Backtest в дэшборде)."""
    base = os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, 'checkpoints')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, 'backtest_history.jsonl')


def append_backtest_history(elapsed_sec, symbols, combos, results,
                            kind='none', is_night_run=False, ts=None, **extra):
    """Дописывает одну строку в журнал прогонов бэктеста (JSONL).

    Нужно, чтобы сравнивать пересчёты не по принтам: вкладка Backtest в
    дэшборде рисует длительность прогонов (полный/частичный) по дням и число
    комбинаций. Ошибка записи не должна ронять бэктест.
    """
    rec = {
        'ts': (ts or datetime.datetime.now()).isoformat(timespec='seconds'),
        # kind сохраняем как есть (full / partial / incremental): дэшборд
        # рисует их отдельными сериями и считает скорость по каждому режиму.
        'kind': kind if kind in ('full', 'partial', 'incremental') else 'none',
        'elapsed_sec': round(float(elapsed_sec), 1),
        'combos': int(combos),
        'combos_done': int(combos),  # факт = план (для partial тоже)
        'combos_plan': int(combos),
        'symbols': int(symbols),
        'symbols_total': int(symbols),  # все символы
        'results': int(results),
        'skipped': 0,  # ничего не пропущено
        'is_night_run': bool(is_night_run),
        **extra,
    }
    try:
        with open(_history_path(), 'a', encoding='utf-8') as f:
            # Реранк по чекпойнтам в журнал НЕ пишем: это чтение
            # кэша, а не пересчёт — вкладке Backtest он не нужен вовсе.
            if rec['kind'] != 'none':
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except OSError as exc:
        print(f"  [WARN] Журнал прогонов не записан: {exc!r}")
    # Режим прогона — наружу: main.py пишет его в таблицу family_status
    # (trades_db). Импорт по имени не годится — значение меняется в рантайме.
    global LAST_RUN_KIND
    LAST_RUN_KIND = rec['kind']
    return rec


# ═══ СТАТУС СЕМЕЙСТВ: кто участвует в ночных рэнкингах ═══
def family_status_rows(symbols, all_results, active, active_strategies,
                       plan_by_family=None, min_score=0.0, run_kind='none',
                       key_fn=None):
    """Строки таблицы family_status: одно (symbol, family) → участие и готовность.

    Источники (все уже под рукой в main.py сразу после реранка):
      * plan_by_family — strategy_combos_per_symbol(strategy_params): план числа
        комбинаций семейства на один символ;
      * чекпойнты символов — сколько комбинаций каждого семейства РЕАЛЬНО посчитано
        (это и есть «участие в ночных рэнкингах»);
      * all_results — комбинации, прошедшие дедупликацию и фильтры (ranking);
      * active + active_strategies — торговый набор и его magic.

    Флаги:
      participates   — семейство есть в плане И посчитано на 100% (полностью
                       участвует в ночных рэнкингах);
      ready_to_trade — есть комбинация в торговом наборе И её score >= min_score
                       (score «совпал» с порогом отбора).

    key_fn — strategy_engine.strategy_key. Передаётся снаружи намеренно: functions.py
    остаётся без зависимости от live-движка (strategy_engine), циклический импорт
    нам не нужен.
    """
    plan_by_family = plan_by_family or {}
    symbols = list(symbols or [])

    def _label(fam):
        try:
            from strategies._registry import label_for as _lf
            _l = _lf(fam)
            if _l:
                return _l
        except Exception:
            pass
        return STRATEGY_COMBO_LABELS.get(fam, fam)

    def _magic(r):
        if key_fn is None:
            return None
        try:
            _k = key_fn(r['symbol'], r.get('param_key'), r.get('type', 'stoch'),
                        r.get('parabolic_max'))
            return (active_strategies.get(_k) or {}).get('magic')
        except Exception:
            return None

    # Посчитано по факту: чекпойнт символа → {family: число комбинаций}
    cached_by_sym = {}
    for sym in symbols:
        res, _bar, _fams = load_checkpoint(sym)
        cnt = {}
        for r in (res or []):
            _t = r.get('type', 'stoch')
            cnt[_t] = cnt.get(_t, 0) + 1
        cached_by_sym[sym] = cnt

    def _group(rows):
        g = {}
        for r in (rows or []):
            g.setdefault((r['symbol'], r.get('type', 'stoch')), []).append(r)
        return g

    ranked_by = _group(all_results)
    active_by = _group(active)

    # Семейства к показу: план ∪ посчитано ∪ в ranking ∪ в active. Символы, которых
    # нет в корзине, но которые есть в ranking/active, тоже показываем — иначе
    # «невидимые» стратегии так и остались бы невидимыми.
    fams_by_sym = {}
    for sym in symbols:
        s = set(plan_by_family.keys())
        s |= set(cached_by_sym.get(sym, {}).keys())
        s |= {f for (sy, f) in ranked_by if sy == sym}
        s |= {f for (sy, f) in active_by if sy == sym}
        fams_by_sym[sym] = s
    for (sy, f) in list(ranked_by.keys()) + list(active_by.keys()):
        fams_by_sym.setdefault(sy, set()).add(f)

    rows = []
    for sym, fams in fams_by_sym.items():
        for fam in sorted(fams):
            planned = int(plan_by_family.get(fam) or 0)
            cached = int(cached_by_sym.get(sym, {}).get(fam) or 0)
            ranked = ranked_by.get((sym, fam), [])
            act = active_by.get((sym, fam), [])
            coverage = (cached / planned * 100.0) if planned > 0 else 0.0
            best = max(ranked, key=lambda x: x.get('score') or 0.0) if ranked else None
            best_score = float(best.get('score') or 0.0) if best else 0.0
            _min = float(min_score or 0.0)
            score_ok = bool(best is not None and best_score >= _min)
            rows.append({
                'symbol': sym,
                'family': fam,
                'label': _label(fam),
                'in_plan': planned > 0,
                'combos_planned': planned,
                'combos_cached': cached,
                'coverage_pct': coverage,
                'participates': bool(planned > 0 and cached >= planned),
                'n_ranked': len(ranked),
                'n_active': len(act),
                'best_param_key': (best or {}).get('param_key', ''),
                'best_score': best_score,
                'min_score': _min,
                'score_ok': score_ok,
                'ready_to_trade': bool(act) and score_ok,
                'magic': _magic(act[0]) if act else None,
                'run_kind': run_kind,
            })
    return rows


# ═══ ЕДИНЫЙ СЧЁТ КОМБИНАЦИЙ ═══
# Пропускная способность бэктеста (замеры journals/run.log, 4 процесса):
# ~5.6 комб/с суммарно ≈ 1.4 комб/с на процесс. Используется для оценки времени.
BACKTEST_COMBOS_PER_SEC_PER_PROCESS = 1.4

# Человекочитаемые названия стратегий для отчёта бюджета (ключи — как в test_strategy).
STRATEGY_COMBO_LABELS = {
    'stoch': 'Stoch', 'parabolic': 'Parabolic', 'ma': 'MA', 'rf': 'RandomForest',
    'logreg': 'LogReg', 'macd_cross': 'MACD-Cross', 'rsi_rev': 'RSI-Rev',
    'bollinger': 'Bollinger', 'ema_cross': 'EMA', 'rsi_div': 'RSI-Div',
    'ichimoku': 'Ichimoku', 'zscore': 'Zscore', 'autocorr': 'Autocorr', 'hurst': 'Hurst',
    'lrc': 'LRC', 'percentile': 'Percentile', 'runs': 'Runs', 'coint': 'Coint',
    'sharpe': 'Sharpe', 'skewness': 'Skewness', 'kurtosis': 'Kurtosis',
    'bayesian': 'Bayesian', 'chi_square': 'ChiSq', 'vwap': 'VWAP', 'momentum': 'Momentum',
    'pin_bar': 'PinBar', 'prev_daily': 'PrevDaily', 'corr_momentum': 'CorrMomentum',
    'williams_r': 'WilliamsR', 'macd_histogram': 'MACD-Hist', 'bb_squeeze': 'BB-Squeeze',
    'donchian': 'Donchian', 'engulfing': 'Engulfing', 'cci': 'CCI', 'supertrend': 'SuperTrend',
    'adx': 'ADX', 'obv': 'OBV', 'morning_star': 'MorningStar',
}


def strategy_combos_per_symbol(sp):
    """Единый источник счёта комбинаций на 1 символ: {strategy_key: combos}.

    Ключи совпадают с test_strategy (легаси) + реестр standalone (ENABLED_BATCH).
    sp — namespace с полями-списками параметров (config.StrategyParams).
    Используется бэктестом (итоги, оценка времени) и отчётом бюджета в main.py,
    чтобы 9018/10503/11043 не расходились.
    """
    m = {
        'stoch': len(sp.k_periods) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'parabolic': len(sp.parabolic_steps) * len(sp.parabolic_maxs) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'ma': len(sp.ma_periods) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'rf': len(sp.rf_lookbacks) * len(sp.rf_nbars) * len(sp.rf_thresholds) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'logreg': len(sp.logreg_lookbacks) * len(sp.logreg_nbars) * len(sp.logreg_thresholds) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'macd_cross': len(sp.macd_cross_fast_list) * len(sp.macd_cross_slow_list) * len(sp.macd_cross_signal_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'rsi_rev': len(sp.rsi_rev_period_list) * len(sp.rsi_rev_oversold_list) * len(sp.rsi_rev_overbought_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'bollinger': len(sp.bb_period_list) * len(sp.bb_std_list) * len(sp.volume_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'ema_cross': len(sp.ema_fast_list) * len(sp.ema_slow_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'rsi_div': len(sp.rsi_div_period_list) * len(sp.rsi_div_lookback_list) * len(sp.rsi_div_threshold_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'ichimoku': len(sp.tenkan_list) * len(sp.kijun_list) * len(sp.senkou_b_list) * len(sp.displacement_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'zscore': len(sp.zscore_sma_period_list) * len(sp.zscore_threshold_list) * len(sp.zscore_vol_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'autocorr': len(sp.autocorr_lag_list) * len(sp.autocorr_threshold_list) * len(sp.autocorr_vol_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'hurst': len(sp.hurst_window_list) * len(sp.hurst_trend_threshold_list) * len(sp.hurst_vol_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'lrc': len(sp.lrc_period_list) * len(sp.lrc_std_threshold_list) * len(sp.lrc_vol_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'percentile': len(sp.pct_period_list) * len(sp.pct_low_list) * len(sp.pct_high_list) * len(sp.pct_vol_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'runs': len(sp.runs_window_list) * len(sp.runs_threshold_list) * len(sp.runs_vol_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'coint': len(sp.coint_window_list) * len(sp.coint_threshold_list) * len(sp.coint_beta_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'sharpe': len(sp.sharpe_window_list) * len(sp.sharpe_threshold_list) * len(sp.sharpe_vol_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'skewness': len(sp.skew_window_list) * len(sp.skew_threshold_list) * len(sp.skew_vol_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'bayesian': len(sp.bayes_window_list) * len(sp.bayes_threshold_list) * len(sp.bayes_prior_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'kurtosis': len(sp.kurt_window_list) * len(sp.kurt_threshold_list) * len(sp.kurt_vol_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'chi_square': len(sp.chisq_window_list) * len(sp.chisq_entry_list) * len(sp.chisq_exit_list) * len(sp.chisq_vol_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'vwap': len(sp.vwap_vol_period_list) * len(sp.vwap_std_mult_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'momentum': len(sp.momentum_period_list) * len(sp.momentum_threshold_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'pin_bar': len(sp.pin_bar_body_ratio_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'prev_daily': len(sp.prev_daily_hold_bars_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'corr_momentum': len(sp.corr_window_list) * len(sp.corr_threshold_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'williams_r': len(sp.williams_r_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'macd_histogram': len(sp.macd_histogram_fast_list) * len(sp.macd_histogram_slow_list) * len(sp.macd_histogram_signal_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'bb_squeeze': len(sp.bb_squeeze_period_list) * len(sp.bb_squeeze_std_list) * len(sp.bb_squeeze_pct_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'donchian': len(sp.donchian_period_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'engulfing': len(sp.engulfing_dummy) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'cci': len(sp.cci_period_list) * len(sp.cci_threshold_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'supertrend': len(sp.supertrend_period_list) * len(sp.supertrend_multiplier_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'adx': len(sp.adx_period_list) * len(sp.adx_threshold_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'obv': len(sp.obv_period_list) * len(sp.obv_threshold_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
        'morning_star': len(sp.morning_star_body_ratio_list) * len(sp.sl_points_list) * len(sp.tp_points_list),
    }
    try:
        from strategies._registry import enabled_combos as _enabled_combos
        m.update(_enabled_combos(sp.sl_points_list, sp.tp_points_list))
    except Exception as exc:
        print(f"  -> [WARN] реестр комбинаций: {exc!r}", flush=True)
    return m


# ═══ Чекпойнт: формат результата ═══
# v1 — только агрегаты комбинации (n_trades, win_rate, profit_factor, score).
# v2 — плюс поле 'trades': журнал сделок [[entry_epoch, exit_epoch, dir, profit], ...].
#      Он и есть основа инкремента по новым барам: агрегаты окно не сдвигают (см.
#      trade_log.py). Файлы v1 читаются как раньше, но по ним инкремент невозможен —
#      символ один раз пересчитывается полностью, дальше пишется v2.
CHECKPOINT_VERSION = 3

# Режим последнего прогона бэктеста (full / incremental / partial / none).
# run_full_backtest выставляет его в конце; main.py читает и пишет в таблицу
# family_status (trades_db), чтобы по каждому семейству было видно, в каком
# режиме оно обсчитывалось. Импортировать значение по имени нельзя — оно
# меняется во время работы, поэтому читаем через модуль.
LAST_RUN_KIND = None


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
    """Загрузить результаты для символа из чекпойнта. Возвращает (results, last_bar_time, families) или (None, None, None)."""
    path = _checkpoint_file(symbol)
    if not os.path.exists(path):
        return None, None, None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Версия модели бэктеста. Меняется при правке самой логики расчёта
        # (например, добавлен своп за удержание) — старые результаты тогда
        # несовместимы, и символ честно уходит в полный пересчёт.
        if data.get('version') != CHECKPOINT_VERSION:
            return None, None, None
        return data.get('results', []), data.get('last_bar_time'), data.get('families')
    except (json.JSONDecodeError, KeyError):
        return None, None, None


def save_checkpoint(symbol, results, last_bar_time=None, families=None):
    """Сохранить результаты для символа в чекпойнт."""
    path = _checkpoint_file(symbol)
    data = {
        'symbol': symbol,
        'timestamp': datetime.datetime.now().isoformat(),
        'n_results': len(results),
        'last_bar_time': last_bar_time,
        'families': families,
        'version': CHECKPOINT_VERSION,
        'results': results
    }
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'), default=json_default)
    except (OSError, TypeError) as exc:
        print(f"  [WARN] Чекпойнт {symbol} не записан ({path}): {exc!r} — "
              f"символ может уйти в пересчёт заново", flush=True)


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
        # Маркеры прогона — не символы: раньше night_reset/last_run/last_full_recalc
        # попадали в список чекпойнтов и ломали проверку «чекпойнтов нет».
        if fname.endswith('.json') and fname not in ('night_reset.json', 'last_run.json',
                                                     'last_full_recalc.json',
                                                     'backtest_history.jsonl'):
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


def _backtest_williams_r(df, period, sl_points, tp_points,
                         point, tick_value, tick_size, spread_points=0):
    """Backtest для Williams %R Extreme."""
    from strategies.williams_r_extreme import backtest as backtest_williams_r
    return backtest_williams_r(df, period, sl_points, tp_points, point,
                               tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_macd_histogram(df, fast_period, slow_period, signal_period,
                             sl_points, tp_points, point, tick_value, tick_size, spread_points=0):
    """Backtest для MACD Histogram Reversal."""
    from strategies.macd_histogram_reversal import backtest as backtest_macd_hist
    return backtest_macd_hist(df, fast_period, slow_period, signal_period,
                              sl_points, tp_points, point, tick_value, tick_size,
                              sim_lot=0.01, spread_points=spread_points)


def _backtest_bb_squeeze(df, bb_period, bb_std, squeeze_pct, sl_points, tp_points,
                         point, tick_value, tick_size, spread_points=0):
    """Backtest для BB Squeeze Breakout."""
    from strategies.bb_squeeze_breakout import backtest as backtest_bb_squeeze
    return backtest_bb_squeeze(df, bb_period, bb_std, squeeze_pct, sl_points, tp_points,
                               point, tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_donchian(df, period, sl_points, tp_points,
                       point, tick_value, tick_size, spread_points=0):
    """Backtest для Donchian Breakout."""
    from strategies.donchian_breakout import backtest as backtest_donchian
    return backtest_donchian(df, period, sl_points, tp_points, point,
                             tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_engulfing(df, sl_points, tp_points,
                        point, tick_value, tick_size, spread_points=0):
    """Backtest для Engulfing Pattern."""
    from strategies.engulfing_pattern import backtest as backtest_engulfing
    return backtest_engulfing(df, sl_points, tp_points, point,
                              tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_cci(df, period, threshold, sl_points, tp_points,
                  point, tick_value, tick_size, spread_points=0):
    """Backtest для CCI Reversion."""
    from strategies.cci_reversion import backtest as backtest_cci
    return backtest_cci(df, period, threshold, sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_supertrend(df, period, multiplier, sl_points, tp_points,
                         point, tick_value, tick_size, spread_points=0):
    """Backtest для SuperTrend."""
    from strategies.supertrend import backtest as backtest_supertrend
    return backtest_supertrend(df, period, multiplier, sl_points, tp_points, point,
                               tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_adx(df, period, adx_threshold, sl_points, tp_points,
                  point, tick_value, tick_size, spread_points=0):
    """Backtest для ADX Trend."""
    from strategies.adx_trend import backtest as backtest_adx
    return backtest_adx(df, period, adx_threshold, sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_obv(df, period, threshold, sl_points, tp_points,
                  point, tick_value, tick_size, spread_points=0):
    """Backtest для OBV Flow."""
    from strategies.obv_flow import backtest as backtest_obv
    return backtest_obv(df, period, threshold, sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot=0.01, spread_points=spread_points)


def _backtest_morning_evening_star(df, min_body_ratio, sl_points, tp_points,
                                   point, tick_value, tick_size, spread_points=0):
    """Backtest для Morning/Evening Star."""
    from strategies.morning_evening_star import backtest as backtest_morning_evening_star
    return backtest_morning_evening_star(df, min_body_ratio, sl_points, tp_points, point,
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


# ═══ Своп за удержание (в бэктесте) ═══
# До этого бэктест считал только спред. Живой отчёт штурвала показал, что
# отрицательный своп — крупная статья расходов и что она системно бьёт по одной
# стороне: USDJPY swap_short = −15.00 пунктов/день против swap_long = −2.50,
# EURUSD swap_short = 0.00. Отбор этого не видел и потому любил JPY-шорты и
# «долгие» часовые стратегии (pin_bar). Считаем по брокерским ставкам.
def _swap_money_per_lot(point, tick_value, tick_size, direction, days,
                        swap_long, swap_short):
    """Своп за удержание позиции: валюта счёта на 1 лот.

    Ставки приходят в ПУНКТАХ за день на лот (swap_mode=1), поэтому
    деньги = пункты × point × (tick_value / tick_size) × дни — та же арифметика,
    что в риск-модели лота (_sl_money_per_lot). Тройной своп по средам
    (swap_rollover3day) не моделируем: оценка выходит на ~10–20% мягче реальной.
    """
    pts = swap_long if direction == 'long' else swap_short
    if not pts or days <= 0 or not point or not tick_size:
        return 0.0
    return pts * point * (tick_value / tick_size) * days


def _apply_swap(out, ctx):
    """Вычитает своп за удержание из каждой сделки результата бэктеста.

    ctx = (point, tick_value, tick_size, sim_lot, swap_long, swap_short) или None.
    Удержание берём из журнала сделок (.times): [t_in, t_out, dir, profit] — времена
    входа/выхода есть только там. Нет журнала (обычный list) или длины не совпали →
    результат не трогаем: подставлять среднее удержание вместо реального хуже, чем
    не считать своп вовсе (такая комбинация и так уходит в полный расчёт).
    Своп пишется и в сам журнал (rec[3]) — иначе инкрементальный пересчёт собрал бы
    метрики обратно без свопа.
    """
    if not ctx or not out or len(out) < 3:
        return out
    profits = out[2]
    times = getattr(profits, 'times', None)
    if not times or len(times) != len(profits):
        return out
    point, tick_value, tick_size, sim_lot, swap_long, swap_short = ctx
    total = 0.0
    for i, rec in enumerate(times):
        days = (rec[1] - rec[0]) / 86400.0
        swap = _swap_money_per_lot(point, tick_value, tick_size,
                                   'long' if rec[2] > 0 else 'short', days,
                                   swap_long, swap_short) * sim_lot
        net = profits[i] - swap
        profits[i] = net
        rec[3] = round(net, 2)
        total += net
    return total, out[1], profits


def _reconstruct_symbol_info(symbol, info_dict):
    """Восстановить объект с полями, которые нужны для бэктеста."""
    class _SymbolInfo:
        __slots__ = ['point', 'trade_tick_value', 'trade_tick_size', 'spread',
                     'swap_long', 'swap_short', 'swap_mode']
        def __init__(self, point, trade_tick_value, trade_tick_size, spread,
                     swap_long=0.0, swap_short=0.0, swap_mode=1):
            self.point = point
            self.trade_tick_value = trade_tick_value
            self.trade_tick_size = trade_tick_size
            self.spread = spread
            self.swap_long = swap_long
            self.swap_short = swap_short
            self.swap_mode = swap_mode
    return _SymbolInfo(info_dict['point'], info_dict['trade_tick_value'],
                       info_dict['trade_tick_size'], info_dict['spread'],
                       info_dict.get('swap_long', 0.0),
                       info_dict.get('swap_short', 0.0),
                       info_dict.get('swap_mode', 1))


def _run_symbol_safe(args):
    """Безопасный запуск бэктеста одного символа: ошибка внутри него
    не роняет весь расчёт — воркер возвращает пустой результат."""
    try:
        _symbol_out = _backtest_symbol(args)
        try:
            from strategies._calc_cache import log_stats as _log_calc_cache
            _log_calc_cache('символ готов')
        except Exception:
            pass
        return _symbol_out
    except Exception as exc:
        symbol = args[1] if len(args) > 1 else '?'
        print(f"\n  [ERROR] Символ {symbol} не рассчитан: {exc!r} — пропускаем",
              flush=True)
        return symbol, [], 0, 0, []


def _backtest_symbol(args):
    """Бэктест одного символа (для multiprocessing)."""
    # ── Инкремент по новым барам (Шаг 2): два прохода в ОДНОМ воркере ──
    # run_full_backtest кладёт метаданные инкремента последним элементом args (dict).
    # Разворачиваем их в два рекурсивных прохода: (1) срез [warm-up .. now] для семейств
    # exact/exp, (2) полное окно для cum/model. Тело ниже не меняется — оно просто
    # вызывается дважды с разными df и фильтром семейств (_FamilyFilter). Каждый проход
    # пишет свой (неполный) чекпойнт; финальный мерж журналов и полный save делает
    # run_full_backtest (шаг «Мерж ИНКРЕМЕНТАЛЬНОГО пересчёта»).
    _inc_meta = args[-1] if (isinstance(args, tuple) and len(args) > 1) else None
    if isinstance(_inc_meta, dict) and _inc_meta.get('inc_families'):
        _base = list(args[:-1])
        _a1 = list(_base)
        _a1[2] = _inc_meta['df_slice']
        _a1[-1] = set(_inc_meta['inc_families'])
        _r1 = _backtest_symbol(tuple(_a1))
        _a2 = list(_base)
        _a2[-1] = set(_inc_meta['full_families'])
        _r2 = _backtest_symbol(tuple(_a2))
        return (_r1[0], list(_r1[1]) + list(_r2[1]),
                int(_r1[2]) + int(_r2[2]), _r1[3],
                list(_r1[4]) + list(_r2[4]))
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
     WILLIAMS_R_PERIOD_LIST, MACD_HISTOGRAM_FAST_LIST, MACD_HISTOGRAM_SLOW_LIST, MACD_HISTOGRAM_SIGNAL_LIST,
     BB_SQUEEZE_PERIOD_LIST, BB_SQUEEZE_STD_LIST, BB_SQUEEZE_PCT_LIST,
     DONCHIAN_PERIOD_LIST, ENGULFING_PERIOD_LIST,
     CCI_PERIOD_LIST, CCI_THRESHOLD_LIST,
     SUPERTREND_PERIOD_LIST, SUPERTREND_MULTIPLIER_LIST,
     ADX_PERIOD_LIST, ADX_THRESHOLD_LIST,
     OBV_PERIOD_LIST, OBV_THRESHOLD_LIST,
     MORNING_STAR_BODY_RATIO_LIST,
     BACKTEST_DAYS, test_strategy, test_mode, total_symbols,

     family_fp, recalc_families, *_extra) = args

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
    williams_r_per_symbol = len(WILLIAMS_R_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    macd_histogram_per_symbol = (len(MACD_HISTOGRAM_FAST_LIST) * len(MACD_HISTOGRAM_SLOW_LIST) *
                                 len(MACD_HISTOGRAM_SIGNAL_LIST) *
                                 len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    bb_squeeze_per_symbol = len(BB_SQUEEZE_PERIOD_LIST) * len(BB_SQUEEZE_STD_LIST) * len(BB_SQUEEZE_PCT_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    donchian_per_symbol = len(DONCHIAN_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    engulfing_per_symbol = len(ENGULFING_PERIOD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    cci_per_symbol = len(CCI_PERIOD_LIST) * len(CCI_THRESHOLD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    supertrend_per_symbol = len(SUPERTREND_PERIOD_LIST) * len(SUPERTREND_MULTIPLIER_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    adx_per_symbol = len(ADX_PERIOD_LIST) * len(ADX_THRESHOLD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    obv_per_symbol = len(OBV_PERIOD_LIST) * len(OBV_THRESHOLD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    morning_star_per_symbol = len(MORNING_STAR_BODY_RATIO_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)

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
        'williams_r': williams_r_per_symbol,
        'macd_histogram': macd_histogram_per_symbol,
        'bb_squeeze': bb_squeeze_per_symbol,
        'donchian': donchian_per_symbol,
        'engulfing': engulfing_per_symbol,
        'cci': cci_per_symbol,
        'supertrend': supertrend_per_symbol,
        'adx': adx_per_symbol,
        'obv': obv_per_symbol,
        'morning_star': morning_star_per_symbol,
    }

    # Реестр standalone (ENABLED_BATCH) — тот же счёт, что в run_full_backtest и main.py,
    # иначе прогресс символа (10503) расходился с итогом (11043).
    try:
        from strategies._registry import enabled_combos as _enabled_combos
        _strategy_map.update(_enabled_combos(SL_POINTS_LIST, TP_POINTS_LIST))
    except Exception as _reg_err:
        print(f"  -> [WARN] реестр комбинаций: {_reg_err}", flush=True)

    if isinstance(test_strategy, str) and test_strategy in _strategy_map:
        active_combos = _strategy_map[test_strategy]
    else:
        active_combos = sum(_strategy_map.values())

    status = "старт" if symbol_idx < 4 else "в очереди"
    print(f"  [{symbol_idx + 1}/{total_symbols}] {symbol}: {status} ({active_combos} комб.)", flush=True)

    results = []
    combos_done = 0

    # ── Свёртка SL/TP: подготовка (calc_*) считается 1 раз на комбинацию параметров,
    # а не на каждую из 9 пар SL/TP (strategies/_calc_cache.py). Сигналы от SL/TP не
    # зависят, а пары идут подряд — 8 вызовов из 9 обслуживаются из кэша.
    # Установка идемпотентна и нужна в КАЖДОМ процессе (родитель + воркеры multiprocessing).
    # Откат: config.BacktestConfig.calc_cache = False (или без правки кода — паритет/EXCLUDE). ──
    try:
        from strategies._calc_cache import install as _install_calc_cache
        _install_calc_cache()
    except Exception as _cc_err:
        print(f"  -> [WARN] calc_cache: {_cc_err}", flush=True)
    completed_strategies = []

    # Чекпойнт v2: журналы сделок в порядке вызовов бэктеста (см. _safe_backtest ниже).
    # Нужны для инкремента по новым барам: из агрегатов окно не сдвинуть.
    _trade_logs = []

    # ── Своп за удержание: контекст на весь символ ──
    # sim_lot=0.01 — как во всех обёртках _backtest_* (лот симуляции). Если брокер
    # отдаёт своп не в пунктах (swap_mode != 1), не угадываем: считаем как раньше
    # и говорим об этом в лог.
    _swap_ctx = None
    _sw_long = getattr(info, 'swap_long', 0.0) or 0.0
    _sw_short = getattr(info, 'swap_short', 0.0) or 0.0
    if getattr(info, 'swap_mode', 1) == 1 and (_sw_long or _sw_short):
        _swap_ctx = (info.point, info.trade_tick_value, info.trade_tick_size,
                     0.01, _sw_long, _sw_short)
    else:
        print(f"  -> [WARN] {symbol}: своп в бэктест не добавлен "
              f"(swap_mode={getattr(info, 'swap_mode', None)}, "
              f"long={_sw_long}, short={_sw_short})", flush=True)

    def _safe_backtest(strategy_name, bt_fn, *args, **kwargs):
        nonlocal combos_done
        try:
            out = bt_fn(*args, **kwargs)
            # Своп за удержание: вычитаем из каждой сделки и из журнала .times.
            out = _apply_swap(out, _swap_ctx)
            # v2: профиты могут прийти как TradeList — тогда времена сделок лежат
            # в .times. Обычный list → журнала нет, комбинация остаётся «полный расчёт».
            try:
                _trade_logs.append(getattr(out[2], 'times', None) if len(out) > 2 else None)
            except Exception:
                _trade_logs.append(None)
            return out
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

    # ── Williams %R Extreme ──
    if not test_strategy or test_strategy == 'williams_r':
        for period, sl, tp in product(
            WILLIAMS_R_PERIOD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('WilliamsR', _backtest_williams_r,
                df_window, period, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'williams_r',
                'param_key': f"per{period}",
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
        completed_strategies.append('WilliamsR')

    # ── MACD Histogram Reversal ──
    if not test_strategy or test_strategy == 'macd_histogram':
        for mf, ms, msig, sl, tp in product(
            MACD_HISTOGRAM_FAST_LIST, MACD_HISTOGRAM_SLOW_LIST, MACD_HISTOGRAM_SIGNAL_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('MACD-Hist', _backtest_macd_histogram,
                df_window, mf, ms, msig, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'macd_histogram',
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
        completed_strategies.append('MACD-Hist')

    # ── BB Squeeze Breakout ──
    if not test_strategy or test_strategy == 'bb_squeeze':
        for bp, bs, sp, sl, tp in product(
            BB_SQUEEZE_PERIOD_LIST, BB_SQUEEZE_STD_LIST, BB_SQUEEZE_PCT_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('BB-Squeeze', _backtest_bb_squeeze,
                df_window, bp, bs, sp, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'bb_squeeze',
                'param_key': f"bp{bp}_bs{bs:.1f}_sp{sp:.1f}",
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
        completed_strategies.append('BB-Squeeze')

    # ── Donchian Breakout ──
    if not test_strategy or test_strategy == 'donchian':
        for period, sl, tp in product(
            DONCHIAN_PERIOD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('Donchian', _backtest_donchian,
                df_window, period, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'donchian',
                'param_key': f"per{period}",
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
        completed_strategies.append('Donchian')

    # ── Engulfing Pattern ──
    if not test_strategy or test_strategy == 'engulfing':
        for sl, tp in product(
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('Engulfing', _backtest_engulfing,
                df_window, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'engulfing',
                'param_key': 'none',
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
        completed_strategies.append('Engulfing')

    # ── CCI Reversion ──
    if not test_strategy or test_strategy == 'cci':
        for period, threshold, sl, tp in product(
            CCI_PERIOD_LIST, CCI_THRESHOLD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('CCI-Reversion', _backtest_cci,
                df_window, period, threshold, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'cci',
                'param_key': f"per{period}_th{threshold}",
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
        completed_strategies.append('CCI-Reversion')

    # ── SuperTrend ──
    if not test_strategy or test_strategy == 'supertrend':
        for period, multiplier, sl, tp in product(
            SUPERTREND_PERIOD_LIST, SUPERTREND_MULTIPLIER_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('SuperTrend', _backtest_supertrend,
                df_window, period, multiplier, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'supertrend',
                'param_key': f"per{period}_mul{multiplier}",
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
        completed_strategies.append('SuperTrend')

    # ── ADX Trend ──
    if not test_strategy or test_strategy == 'adx':
        for period, adx_threshold, sl, tp in product(
            ADX_PERIOD_LIST, ADX_THRESHOLD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('ADX-Trend', _backtest_adx,
                df_window, period, adx_threshold, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'adx',
                'param_key': f"per{period}_th{adx_threshold}",
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
        completed_strategies.append('ADX-Trend')

    # ── OBV Flow ──
    if not test_strategy or test_strategy == 'obv':
        for period, threshold, sl, tp in product(
            OBV_PERIOD_LIST, OBV_THRESHOLD_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('OBV-Flow', _backtest_obv,
                df_window, period, threshold, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'obv',
                'param_key': f"per{period}_th{threshold}",
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
        completed_strategies.append('OBV-Flow')

    # ── Morning / Evening Star ──
    if not test_strategy or test_strategy == 'morning_star':
        for min_body_ratio, sl, tp in product(
            MORNING_STAR_BODY_RATIO_LIST,
            SL_POINTS_LIST, TP_POINTS_LIST
        ):
            profit, n_trades, trade_profits = _safe_backtest('MorningStar', _backtest_morning_evening_star,
                df_window, min_body_ratio, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': 'morning_star',
                'param_key': f"br{min_body_ratio}",
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
        completed_strategies.append('MorningStar')

    # ── Сохраняем чекпойнт после каждого символа ──
    last_bar_time = df_window.index[-1].isoformat() if df_window is not None else None

    # save_checkpoint перенесён НИЖЕ — ПОСЛЕ generic-цикла реестра (результаты попадают в чекпойнт)

    # ── Реестр standalone-стратегий (strategies/_registry.py) ──
    # Generic-цикл: добавляет новые стратегии в результаты/ранжирование без
    # дублирования блоками по 28 строк. Ярлык/сетка берутся из реестра.
    try:
        from strategies._registry import REGISTRY as _REG, registry_backtest as _reg_bt
        from strategies._registry import enabled_entries as _enabled_entries
        # БАТЧ-1 (15.10): 20 включённых стратегий из ENABLED_BATCH (strategies/_registry.py).
        # Включение порциями — чтобы не раздувать ночной пересчёт (540 комб. на символ).
        _reg_entries = _enabled_entries()
    except Exception as _reg_err:
        _reg_entries = []
        print(f"  [WARN] реестр стратегий недоступен: {_reg_err}", flush=True)

    for _key, _e in _reg_entries:
        # Семейства реестра лежат в family_fp и под label, и под ключом —
        # фильтр инкрементального пересчёта должен принимать оба имени.
        if test_strategy and test_strategy != _key and test_strategy != _e['label']:
            continue
        for _pk, _sl, _tp in product(_e['grid'], SL_POINTS_LIST, TP_POINTS_LIST):
            profit, n_trades, trade_profits = _safe_backtest(
                _e['label'], _reg_bt, _key,
                df_window, _pk, _sl, _tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            metrics = calc_metrics(trade_profits)
            score = composite_score(metrics)
            results.append({
                'symbol': symbol, 'type': _key, 'param_key': _pk,
                'parabolic_max': None,
                'sl_points': _sl, 'tp_points': _tp,
                'profit': profit, 'n_trades': n_trades,
                'profit_factor': metrics['profit_factor'],
                'max_drawdown': metrics['max_drawdown'],
                'win_rate': metrics['win_rate'],
                'sharpe': metrics['sharpe'],
                'recovery': metrics['recovery'],
                'score': score,
            })
            combos_done += 1
        completed_strategies.append(_e['label'])
        _strategy_map[_key] = len(_e['grid']) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)

    # ── Чекпойнт v2: привязать журналы сделок к комбинациям ──
    # Пары «результат ↔ журнал» выравниваются по порядку вызовов бэктеста: каждая
    # семья в product(...) добавляет ровно один результат на один вызов. Если длины
    # разошлись — журналы НЕ пишем (WARN): символ останется на полном расчёте, но
    # ничего не сломается и не разъедется молча.
    if _trade_logs and len(_trade_logs) == len(results):
        _attached = 0
        for _r, _t in zip(results, _trade_logs):
            if _t is not None:
                _r['trades'] = _t
                _attached += 1
        print(f"  ✔ Чекпойнт v2: журналы сделок записаны для {_attached}/{len(results)} комб.",
              flush=True)
    elif _trade_logs:
        print(f"  [WARN] {symbol}: журналов {len(_trade_logs)} ≠ результатов {len(results)} — "
              f"пишем чекпойнт БЕЗ сделок (инкремент для символа отключён)", flush=True)

    save_checkpoint(symbol, results, last_bar_time=last_bar_time, families=family_fp)

    return symbol, results, combos_done, active_combos, completed_strategies



def backtest_worker_count(backtest_config):
    """Число процессов пересчёта.

    В фоновом режиме (config.async_backtest) пересчёт живёт рядом с боевым циклом и
    терминалом, поэтому одно ядро оставляем циклу: опрос тиков и торговые вызовы не
    должны ждать CPU. Без фонового режима — как раньше (до 4 процессов).
    """
    cpu = max(1, os.cpu_count() or 1)
    reserve = 1 if getattr(backtest_config, 'async_backtest', False) else 0
    return min(4, max(1, cpu - reserve))


def _worker_init():
    """Инициализатор воркера пула пересчёта: BELOW_NORMAL приоритет процесса.

    Воркеры считают 150–230 мин подряд; при обычном приоритете они отбирают CPU у
    главного цикла и терминала. Понижение приоритета (Windows) снимает это без
    потери скорости пересчёта: свободные ядра воркеры по-прежнему занимают полностью.
    """
    try:
        import ctypes
        BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
        kernel32 = ctypes.windll.kernel32
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass  # не Windows / нет прав — считаем как обычно


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

    # ── SL/TP пер-символьно (config.SL_POINTS_GRID) ──
    # Одна полоса в % цены даёт РАЗНЫЕ пункты у пар (point 0.00001 у 5-значных против
    # 0.001 у JPY), поэтому списки выше — только фолбэк для символа вне словаря.
    # Перебор комбинаций в воркере получает списки аргументами, так что резолва здесь
    # достаточно для всех product(..., SL_POINTS_LIST, TP_POINTS_LIST) внутри него.
    try:
        from config import sl_tp_points_for as _sl_tp_for
    except ImportError:      # старый config без пер-символьной сетки
        _sl_tp_for = None

    def _points_for(sym):
        """(SL, TP) в пунктах для символа: из config.SL_POINTS_GRID либо фолбэк."""
        if _sl_tp_for is not None:
            return _sl_tp_for(sym)
        return SL_POINTS_LIST, TP_POINTS_LIST

    def _fp_for_symbol(fp_map, sl_pts, tp_pts):
        """Отпечатки семейств с SL/TP ИМЕННО этого символа.

        В каждом отпечатке SL/TP — последние два элемента (см. family_fp ниже), поэтому
        подменяется только хвост. Без этого чекпойнт, посчитанный с прежней сеткой
        (300/750/1200), считался бы валидным при инкрементальном пересчёте.
        """
        _old_sl, _old_tp = tuple(SL_POINTS_LIST), tuple(TP_POINTS_LIST)
        _new_sl, _new_tp = tuple(sl_pts), tuple(tp_pts)
        out = {}
        for _k, _v in fp_map.items():
            if len(_v) >= 2 and _v[-2] == _old_sl and _v[-1] == _old_tp:
                out[_k] = tuple(_v[:-2]) + (_new_sl, _new_tp)
            else:               # форма отпечатка другая — не трогаем (безопасный путь)
                out[_k] = _v
        return out
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
    WILLIAMS_R_PERIOD_LIST = strategy_params.williams_r_period_list
    MACD_HISTOGRAM_FAST_LIST = strategy_params.macd_histogram_fast_list
    MACD_HISTOGRAM_SLOW_LIST = strategy_params.macd_histogram_slow_list
    MACD_HISTOGRAM_SIGNAL_LIST = strategy_params.macd_histogram_signal_list
    BB_SQUEEZE_PERIOD_LIST = strategy_params.bb_squeeze_period_list
    BB_SQUEEZE_STD_LIST = strategy_params.bb_squeeze_std_list
    BB_SQUEEZE_PCT_LIST = strategy_params.bb_squeeze_pct_list
    DONCHIAN_PERIOD_LIST = strategy_params.donchian_period_list
    ENGULFING_PERIOD_LIST = strategy_params.engulfing_dummy
    CCI_PERIOD_LIST = strategy_params.cci_period_list
    CCI_THRESHOLD_LIST = strategy_params.cci_threshold_list
    SUPERTREND_PERIOD_LIST = strategy_params.supertrend_period_list
    SUPERTREND_MULTIPLIER_LIST = strategy_params.supertrend_multiplier_list
    ADX_PERIOD_LIST = strategy_params.adx_period_list
    ADX_THRESHOLD_LIST = strategy_params.adx_threshold_list
    OBV_PERIOD_LIST = strategy_params.obv_period_list
    OBV_THRESHOLD_LIST = strategy_params.obv_threshold_list
    MORNING_STAR_BODY_RATIO_LIST = strategy_params.morning_star_body_ratio_list
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
    williams_r_per_symbol = (len(WILLIAMS_R_PERIOD_LIST) *
                             len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    macd_histogram_per_symbol = (len(MACD_HISTOGRAM_FAST_LIST) * len(MACD_HISTOGRAM_SLOW_LIST) *
                                 len(MACD_HISTOGRAM_SIGNAL_LIST) *
                                 len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    bb_squeeze_per_symbol = (len(BB_SQUEEZE_PERIOD_LIST) * len(BB_SQUEEZE_STD_LIST) *
                             len(BB_SQUEEZE_PCT_LIST) *
                             len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    donchian_per_symbol = (len(DONCHIAN_PERIOD_LIST) *
                           len(SL_POINTS_LIST) * len(TP_POINTS_LIST))
    engulfing_per_symbol = (len(ENGULFING_PERIOD_LIST) *
                            len(SL_POINTS_LIST) * len(TP_POINTS_LIST))

    cci_per_symbol = len(CCI_PERIOD_LIST) * len(CCI_THRESHOLD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    supertrend_per_symbol = len(SUPERTREND_PERIOD_LIST) * len(SUPERTREND_MULTIPLIER_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    adx_per_symbol = len(ADX_PERIOD_LIST) * len(ADX_THRESHOLD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    obv_per_symbol = len(OBV_PERIOD_LIST) * len(OBV_THRESHOLD_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)
    morning_star_per_symbol = len(MORNING_STAR_BODY_RATIO_LIST) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)

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
        'williams_r': williams_r_per_symbol,
        'macd_histogram': macd_histogram_per_symbol,
        'bb_squeeze': bb_squeeze_per_symbol,
        'donchian': donchian_per_symbol,
        'engulfing': engulfing_per_symbol,
    }

    strat_combo_map.update({
        'cci': cci_per_symbol,
        'supertrend': supertrend_per_symbol,
        'adx': adx_per_symbol,
        'obv': obv_per_symbol,
        'morning_star': morning_star_per_symbol,
    })

    # ── Реестр standalone-стратегий: комбинации для итогов и прогресса ──
    try:
        from strategies._registry import registry_combos as _reg_combos
        from strategies._registry import enabled_combos as _enabled_combos
        # БАТЧ-1: комбинации включённых стратегий учитываем в прогресс-баре и оценке времени
        strat_combo_map.update(_enabled_combos(SL_POINTS_LIST, TP_POINTS_LIST))
    except Exception as _reg_err:
        print(f"  -> [WARN] реестр комбинаций: {_reg_err}", flush=True)

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
        'williams_r': _fp(WILLIAMS_R_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'macd_histogram': _fp(MACD_HISTOGRAM_FAST_LIST, MACD_HISTOGRAM_SLOW_LIST, MACD_HISTOGRAM_SIGNAL_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'bb_squeeze': _fp(BB_SQUEEZE_PERIOD_LIST, BB_SQUEEZE_STD_LIST, BB_SQUEEZE_PCT_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'donchian': _fp(DONCHIAN_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'engulfing': _fp(ENGULFING_PERIOD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'cci': _fp(CCI_PERIOD_LIST, CCI_THRESHOLD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'supertrend': _fp(SUPERTREND_PERIOD_LIST, SUPERTREND_MULTIPLIER_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'adx': _fp(ADX_PERIOD_LIST, ADX_THRESHOLD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'obv': _fp(OBV_PERIOD_LIST, OBV_THRESHOLD_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
        'morning_star': _fp(MORNING_STAR_BODY_RATIO_LIST, SL_POINTS_LIST, TP_POINTS_LIST),
    }

    # ── Реестр standalone-стратегий: отпечатки семейств для чекпойнтов ──
    try:
        from strategies._registry import registry_families as _reg_families
        from strategies._registry import enabled_family_fp_items as _enabled_fp_items
        for _lab, _grids in _enabled_fp_items(SL_POINTS_LIST, TP_POINTS_LIST):  # БАТЧ-1: отпечатки включённых семейств (label + ключ)
            family_fp[_lab] = _fp(*_grids)
    except Exception as _reg_err:
        print(f"  -> [WARN] реестр семейств: {_reg_err}", flush=True)

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
    # ЛОГИКА (режим задаёт вызывающий код):
    # force_recalc=True + is_night_run=True → ПОЛНЫЙ пересчёт (выходные / ручной запуск).
    # force_recalc=False → реранк: чекпойнты/кэш (инкремент в будни).
    if not force_recalc:
        # force_recalc=False — полный пересчёт отключён, только реранк по чекпойнтам
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
            with _safe_marker_write(night_reset_path, 'night_reset.json') as f:
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
            print(f"\n  ✅ Ночной пересчёт по чекпойнтам: night_reset.json {last_night_reset.strftime('%d.%m %H:%M')} — сетка не пересчитывалась")
        else:
            print(f"\n  🌙 нет кэша прошлого прогона — считаем ВСЕ стратегии заново")

    # ── Планирование ИНКРЕМЕНТА по новым барам (Шаг 2) ──
    # Ничего не считает: решает, применим ли инкремент к символу, и готовит срез.
    # Возвращает метаданные для _backtest_symbol либо None (тогда символ идёт как
    # раньше — из кэша / полным окном). Включается флагом config.incremental_bars и
    # только после parity-проверки (strategies/_warmup.py).
    def _plan_incremental(symbol, cached, cached_bar_time, current_bar_time, df, _family_fp, cfg):
        # ИНКРЕМЕНТ УДАЛЁН ИЗ ПРОЕКТА: считаем только ПОЛНЫЕ пересчёты.
        if True:
            return None
        try:
            import trade_log as _tl
            from strategies._warmup import warmup_bars, can_use_incremental
        except Exception as _e:
            print(f"  [WARN] инкремент недоступен: {_e}", flush=True)
            return None
        if not cached or df is None or df.empty:
            return None
        # Бар кэша в индексе текущего df → сколько НОВЫХ баров появилось.
        try:
            _cached_ts = datetime.datetime.fromisoformat(cached_bar_time)
            _cached_epoch = int(_cached_ts.timestamp())
            _pos = int(df.index.get_loc(_cached_ts))
        except (TypeError, ValueError, KeyError):
            return None
        bars_new = len(df) - 1 - _pos
        if bars_new <= 0:
            return None
        # Журналы v2 по типам семейств: есть у ВСЕХ комбинаций семейства?
        _by_type = {}
        for _r in cached:
            _by_type.setdefault(_r.get('type', 'stoch'), []).append(_r)
        _ck_dir = _checkpoint_dir()
        _win = BACKTEST_DAYS * 24
        _w_override = int(getattr(cfg, 'incremental_warmup_bars', 0) or 0)
        inc_families, full_families, max_w = set(), set(), 0
        for _fam, _rows in _by_type.items():
            _capable = bool(_rows) and all(
                ('trades' in _r and isinstance(_r.get('trades'), list)) for _r in _rows)
            if not (_capable and can_use_incremental(_ck_dir, _fam, None, 0, _win)):
                full_families.add(_fam)
                continue
            _w = _w_override or int(warmup_bars(_fam, None, 0, _win) or 0)
            if _w <= 0:
                full_families.add(_fam)
                continue
            inc_families.add(_fam)
            max_w = max(max_w, _w)
        # Нужны ОБА набора: полный набор — ещё и контрольная точка, что окно считается
        # целиком (семейства cum/model инкременту не подлежат по определению).
        if not inc_families or not full_families:
            return None
        _slice_bars = max_w + bars_new
        if _slice_bars >= _win:
            return None    # срез не короче полного окна — выигрыша нет
        _last_epoch = int(df.index[-1].timestamp())
        return {
            'cached': cached,
            'cached_bar_epoch': _cached_epoch,
            'window_start': _last_epoch - _win * 3600,
            'inc_families': inc_families,
            'full_families': full_families,
            'df_slice': df.iloc[-_slice_bars:],
            'bars_new': bars_new,
            'warmup_bars': max_w,
            'slice_bars': _slice_bars,
        }

    # ═══ ЗАГРУЗКА ЧЕКПОЙНТОВ ═══
    existing_checkpoints = list_checkpoints()
    skipped_symbols = {}
    incomplete_symbols = []   # символы с НЕПОЛНЫМ чекпойнтом (меньше комбинаций, чем ожидается)
    partial_recalc = {}
    incremental_recalc = {}   # символ -> метаданные инкремента по новым барам (см. _plan_incremental)
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
        # Полнота проверяется посерийно ниже (см. _broken): кэш НЕ обнуляем,
        # недостающие/оборванные семейства досчитываем, остальные берём из кэша.
        
            
            
        if not cached:   # None (нет файла/битый/другая версия) ИЛИ [] — символ в полный пересчёт

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

        # Полнота по числу комбинаций: семейство могло оборваться в середине (прогон прервался).
        # Досчитываем ТОЛЬКО оборванные семейства, остальной кэш сохраняем (инкремент).
        _type_counts = {}
        for _r in cached:
            _t = _r.get('type', 'stoch')
            _type_counts[_t] = _type_counts.get(_t, 0) + 1
        _broken = [f for f, _exp in strat_combo_map.items()
                   if f in cached_fams and _type_counts.get(f, 0) < _exp]
        if _broken:
            incomplete_symbols.append(symbol)
            recalc_set.update(_broken)

        if cached_bar_time == current_bar_time:
            # Данные не изменились с ночного пересчёта
            if not recalc_set:
                # Конфиг тот же, данные те же — кэш полностью валиден
                cached_results.extend(cached)
                skipped_symbols[symbol] = len(cached)
            else:
                # Данные те же, но конфиг изменился — частичный пересчёт
                # ПАРТИАЛЬНЫЙ ПЕРЕСЧЁТ УДАЛЁН: символ уходит в ПОЛНЫЙ пересчёт.
                continue
        else:
            # Данные изменились после ночного пересчёта
            if not recalc_set:
                # Конфиг не менялся: сперва пробуем ИНКРЕМЕНТ по новым барам. Если он
                # применим, символ уходит в incremental_recalc и НЕ попадает ни в skipped
                # (кэш), ни в partial (пересчёт по семействам).
                _inc_plan = _plan_incremental(symbol, cached, cached_bar_time,
                                              current_bar_time, symbol_data[symbol]['df_h1'],
                                              family_fp, backtest_config)
                if _inc_plan is not None:
                    incremental_recalc[symbol] = _inc_plan
                    continue
                # Инкремент выключен/неприменим — переиспользуем кэш как есть
                cached_results.extend(cached)
                skipped_symbols[symbol] = len(cached)
                reuse_stale.append(symbol)
                print(f"  ℹ {symbol}: кэш рассчитан на баре {cached_bar_time}, "
                      f"сейчас {current_bar_time} — по новым барам не пересчитываем "
                      f"(полный проход — раз в неделю, в окне выходных)", flush=True)
            else:
                # Конфиг изменился + данные изменились — частичный пересчёт
                # ПАРТИАЛЬНЫЙ ПЕРЕСЧЁТ УДАЛЁН: символ уходит в ПОЛНЫЙ пересчёт.
                continue

    # ── Вывод статуса чекпойнтов (компактный) ──
    actions_summary = []

    if force_recalc and not is_night_run:
        actions_summary.append("⚡ Принудительный пересчёт — чекпойнты игнорируются")

    if not force_full_recalc and not existing_checkpoints:
        actions_summary.append("ℹ Чекпойнтов нет — будет полный пересчёт")

    if incomplete_symbols:
        actions_summary.append(
            f"⚠️ Кэш оборван у {len(incomplete_symbols)} симв.: "
            f"{', '.join(incomplete_symbols)} — досчитываем оборванные семейства"
        )

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
        _ck_expected = len(skipped_symbols) * combos_per_symbol
        _ck_status = "ПОЛНЫЕ ✅" if total_results >= _ck_expected else "НЕПОЛНЫЕ ⚠"
        actions_summary.append(
            f"📦 Чекпойнты: {len(skipped_symbols)} символов, {total_results:,} из {_ck_expected:,} комб. — {_ck_status}"
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

    total_symbols = len(valid_symbols)                      # к пересчёту в этом прогоне
    basket_symbols = total_symbols + len(skipped_symbols)   # вся корзина (пересчёт + чекпойнты)

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
            # Своп за удержание: брокер отдаёт ставки в пунктах за день (swap_mode=1).
            'swap_long': getattr(info, 'swap_long', 0.0) or 0.0,
            'swap_short': getattr(info, 'swap_short', 0.0) or 0.0,
            'swap_mode': getattr(info, 'swap_mode', 1),
        }
        df_window = sd['df_h1'].tail(BACKTEST_DAYS * 24)
        # SL/TP и отпечатки — от ЭТОГО символа (сетка пер-символьная).
        _sl_pts, _tp_pts = _points_for(symbol)
        _fp_sym = _fp_for_symbol(family_fp, _sl_pts, _tp_pts)
        symbol_args.append((
            idx, symbol, df_window, info_dict, K_PERIODS, _sl_pts, _tp_pts,
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
            WILLIAMS_R_PERIOD_LIST, MACD_HISTOGRAM_FAST_LIST, MACD_HISTOGRAM_SLOW_LIST, MACD_HISTOGRAM_SIGNAL_LIST,
            BB_SQUEEZE_PERIOD_LIST, BB_SQUEEZE_STD_LIST, BB_SQUEEZE_PCT_LIST,
            DONCHIAN_PERIOD_LIST, ENGULFING_PERIOD_LIST,
            CCI_PERIOD_LIST, CCI_THRESHOLD_LIST,
            SUPERTREND_PERIOD_LIST, SUPERTREND_MULTIPLIER_LIST,
            ADX_PERIOD_LIST, ADX_THRESHOLD_LIST,
            OBV_PERIOD_LIST, OBV_THRESHOLD_LIST,
            MORNING_STAR_BODY_RATIO_LIST,


            BACKTEST_DAYS, test_strategy, test_mode, total_symbols,
            _fp_sym, partial_recalc.get(symbol, (None, None))[1],
            ({_k: _v for _k, _v in incremental_recalc[symbol].items() if _k != 'cached'}
             if symbol in incremental_recalc else None)
        ))

    total_combos = combos_per_symbol * total_symbols          # работа в этом прогоне (к пересчёту)
    combos_plan = combos_per_symbol * basket_symbols          # полный план корзины
    n_skipped = len(skipped_symbols)

    # ── Вывод плана бэктеста ──
    print(f"\n{'═' * 60}")
    if n_skipped > 0:
        print(f"  БЭКТЕСТ | {basket_symbols} символов в корзине × {combos_per_symbol} комб. = {combos_plan} всего")
        print(f"  ⏭ Из чекпойнтов: {n_skipped} симв. | к пересчёту: {total_symbols} симв. = {total_combos} комб.")
    else:
        print(f"  БЭКТЕСТ | {basket_symbols} символов в корзине × {combos_per_symbol} комб. = {combos_plan} всего")
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
    if not test_strategy or test_strategy == 'williams_r':
        strategies_to_run.append(("WilliamsR", williams_r_per_symbol))
    if not test_strategy or test_strategy == 'macd_histogram':
        strategies_to_run.append(("MACD-Hist", macd_histogram_per_symbol))
    if not test_strategy or test_strategy == 'bb_squeeze':
        strategies_to_run.append(("BB-Squeeze", bb_squeeze_per_symbol))
    if not test_strategy or test_strategy == 'donchian':
        strategies_to_run.append(("Donchian", donchian_per_symbol))
    if not test_strategy or test_strategy == 'engulfing':
        strategies_to_run.append(("Engulfing", engulfing_per_symbol))
    if not test_strategy or test_strategy == 'cci':
        strategies_to_run.append(("CCI-Reversion", cci_per_symbol))
    if not test_strategy or test_strategy == 'supertrend':
        strategies_to_run.append(("SuperTrend", supertrend_per_symbol))
    if not test_strategy or test_strategy == 'adx':
        strategies_to_run.append(("ADX-Trend", adx_per_symbol))
    if not test_strategy or test_strategy == 'obv':
        strategies_to_run.append(("OBV-Flow", obv_per_symbol))
    if not test_strategy or test_strategy == 'morning_star':
        strategies_to_run.append(("MorningStar", morning_star_per_symbol))

    # ── Реестр standalone-стратегий (strategies/_registry.py) ──
    try:
        from strategies._registry import REGISTRY as _REG_SR
        from strategies._registry import enabled_entries as _enabled_entries_sr
        for _k, _e in _enabled_entries_sr():  # БАТЧ-1: включённые стратегии реестра
            # При инкрементальном пересчёте фильтр сравнивает по label — принимаем оба имени
            if not test_strategy or test_strategy == _k or test_strategy == _e['label']:
                strategies_to_run.append((_e['label'], len(_e['grid']) * len(SL_POINTS_LIST) * len(TP_POINTS_LIST)))
    except Exception as _reg_err:
        print(f"  -> [WARN] реестр (список стратегий): {_reg_err}", flush=True)

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
            _est_procs = backtest_worker_count(backtest_config)
            est_sec = max(1, int(total_combos / (_est_procs * BACKTEST_COMBOS_PER_SEC_PER_PROCESS)))
            est_note = (f"грубая оценка: ~{BACKTEST_COMBOS_PER_SEC_PER_PROCESS:g} комб/с на процесс "
                        f"× {_est_procs} процессов (по замерам run.log)")
        print(f"  ⏱  Ориентировочно расчёт займёт ~{est_sec / 60:.0f} минут. {est_note}")
    elif total_symbols == 0:
        print(f"  ✅ Всё готово из чекпойнтов — расчёт не нужен")
    print(f"{'═' * 60}")

    # ── Запуск бэктеста ──
    n_processes = backtest_worker_count(backtest_config)
    use_multiprocessing = len(symbol_args) > 1

    results_list = []
    done = 0

    if use_multiprocessing:
        print(f"\n  Multiprocessing: {n_processes} процессов\n")
        import multiprocessing as mp
        with mp.Pool(processes=n_processes, initializer=_worker_init) as pool:
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
    # ФАКТ посчитанных комбинаций (total_combos — работа к пересчёту; combos_plan — вся корзина)
    combos_done_total = sum(int((it[2] if len(it) > 2 else 0) or 0) for it in results_list)

    all_results = list(cached_results)   # ← начинаем с кэша пропущенных
    new_by_symbol = {}
    for item in results_list:
        symbol, results, combos_done, active_combos, completed_strategies = item
        new_by_symbol.setdefault(symbol, []).extend(results)

    # ── Сводка по инкременту (для журнала прогонов / вкладки Backtest) ──
    # Нужна, чтобы в дэшборде был виден масштаб ночи: сколько семейств считалось
    # срезом, сколько полным окном, на каком срезе и сколько комбинаций обновлено.
    _inc_stat = None
    if False:  # инкремент удалён из проекта: ветка недостижима
        _inc_vals = list(incremental_recalc.values())
        _inc_stat = {
            'inc_symbols': len(_inc_vals),
            'inc_families': sum(len(m.get('inc_families') or ()) for m in _inc_vals),
            'full_families': sum(len(m.get('full_families') or ()) for m in _inc_vals),
            'slice_bars': max([int(m.get('slice_bars') or 0) for m in _inc_vals] or [0]),
            'warmup_bars': max([int(m.get('warmup_bars') or 0) for m in _inc_vals] or [0]),
            'bars_new': max([int(m.get('bars_new') or 0) for m in _inc_vals] or [0]),
            'window_bars': int(getattr(backtest_config, 'backtest_days', 0) or 0) * 24,
            'inc_combos': 0,
        }

    # ── Мерж ИНКРЕМЕНТАЛЬНОГО пересчёта (новые бары) ──
    # Воркер посчитал: семейства inc — на срезе, full — полным окном. Журналы inc
    # склеиваем с журналами кэша (trade_log.merge_incremental), метрики пересчитываем
    # ИЗ ПРОФИТОВ (агрегаты окно не сдвигают), чекпойнт сохраняем ПОЛНЫЙ.
    if False:  # инкремент удалён из проекта: ветка недостижима
        from strategy_engine import calc_metrics as _calc_m, composite_score as _comp_s
        import trade_log as _tl
        for symbol, meta in incremental_recalc.items():
            cached = meta['cached']
            inc_fams = meta['inc_families']
            _by_key = {}
            for _r in new_by_symbol.get(symbol, []):
                _by_key[(_r.get('type', 'stoch'), _r.get('param_key'), _r.get('parabolic_max'),
                         _r.get('sl_points'), _r.get('tp_points'))] = _r
            _merged = []
            _upd = 0
            for r0 in cached:
                _key = (r0.get('type', 'stoch'), r0.get('param_key'),
                        r0.get('parabolic_max'), r0.get('sl_points'), r0.get('tp_points'))
                r1 = _by_key.get(_key)
                if r0.get('type', 'stoch') not in inc_fams:
                    _merged.append(r1 if r1 is not None else r0)   # семейство полного прохода
                    continue
                if r1 is None:
                    _merged.append(r0)                             # страховка: нет новой версии
                    continue
                _tr = _tl.merge_incremental(r0.get('trades'), r1.get('trades'),
                                            meta['cached_bar_epoch'], meta['window_start'])
                _pr = _tl.profits(_tr)
                _m = _calc_m(_pr)
                r1 = dict(r1)
                r1['trades'] = _tr
                r1['profit'] = round(sum(_pr), 2)
                r1['n_trades'] = len(_pr)
                r1['profit_factor'] = _m['profit_factor']
                r1['max_drawdown'] = _m['max_drawdown']
                r1['win_rate'] = _m['win_rate']
                r1['sharpe'] = _m['sharpe']
                r1['recovery'] = _m['recovery']
                r1['score'] = _comp_s(_m)
                _merged.append(r1)
                _upd += 1
                if _inc_stat is not None:
                    _inc_stat['inc_combos'] += 1
            all_results.extend(_merged)
            try:
                save_checkpoint(symbol, _merged,
                                last_bar_time=symbol_data[symbol]['df_h1'].index[-1].isoformat(),
                                families=family_fp)
            except (OSError, TypeError):
                pass
            print(f"  🔄 {symbol}: инкремент по новым барам — обновлено {_upd} комб., "
                  f"inc-семейств {len(inc_fams)}, full-семейств {len(meta['full_families'])} "
                  f"(срез {meta['slice_bars']} бар. = warm-up {meta['warmup_bars']} + новых {meta['bars_new']})",
                  flush=True)

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
    # Диверсификация рейтинга: стратегии одного типа разносим по рейтингу
    # (round-robin по типам), чтобы в топе не стоял сплошной RF/LogReg и т.п.
    _by_type = {}
    for r in all_results:
        _by_type.setdefault(r.get('type', 'stoch'), []).append(r)
    for _lst in _by_type.values():
        _lst.sort(key=lambda x: x['score'], reverse=True)
    all_results = []
    while _by_type:
        for _t in list(_by_type.keys()):
            if not _by_type[_t]:
                del _by_type[_t]
                continue
            all_results.append(_by_type[_t].pop(0))

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
        # ═══ Журнал прогонов (вкладка Backtest в дэшборде) ═══
        append_backtest_history(
            total_elapsed, total_symbols, total_combos, len(all_results),
            combos_done=combos_done_total,
            symbols_total=basket_symbols,
            combos_plan=combos_plan,
            kind=('full' if force_full_recalc
                  else 'none'),
                  # partial/инкремент удалены из проекта: пишем только 'full', а
                  # прогон по кэшу (реранк) в журнал не попадает вовсе.
            skipped=len(skipped_symbols),
            ok=True,
            is_night_run=is_night_run,
            inc=(_inc_stat or {}),
            inc_applied=bool(_inc_stat),
        )

        with _safe_marker_write(last_run_path, 'last_run.json') as f:
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
            with _safe_marker_write(night_reset_path, 'night_reset.json') as f:
                json.dump({
                    'timestamp': now.isoformat(),
                    'status': 'completed',
                    # К какому ночному окну (03:00) относится прогон — timestamp выше
                    # теперь реальный, поэтому окно вынесено отдельным полем.
                    'night_window': now.replace(hour=3, minute=0, second=0,
                                                microsecond=0).isoformat(),
                    'symbols': total_symbols,
                    'total_results': len(all_results),
                    'elapsed_sec': round(total_elapsed, 1),
                }, f, ensure_ascii=False, indent=2)
            print(f"\n  🌙 Ночной пересчёт завершён: {total_symbols} символов, {len(all_results)} стратегий")
            print(f"  📅 Timestamp: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        except (OSError, TypeError):
            pass

    return top_results, all_results

