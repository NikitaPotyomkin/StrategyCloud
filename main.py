import MetaTrader5 as mt5
from datetime import datetime, timedelta, date
import os
import csv
import time
import socket
import json
import warnings
from collections import defaultdict

warnings.filterwarnings('ignore')

# Логирование прогона в journals/run.log (stdout+stderr с ротацией).
# Fail-safe: любая проблема с логом не должна ронять пайплайн.
try:
    import run_log
    try:
        run_log.setup()
    except Exception:
        # Не глушим молча: без файлового лога весь прогон не оставит следов в journals/.
        import sys as _sys
        print(f"[WARN] Лог journals/run.log не открылся ({_sys.exc_info()[1]!r}) — "
              f"прогон продолжится без файлового лога", flush=True)
except Exception:
    pass




from functions import (terminal_on, run_full_backtest, backtest_worker_count,
                        _checkpoint_dir, family_status_rows, strategy_combos_per_symbol,
                        _safe_marker_write)
from daily_report import generate_daily_report, generate_missing_reports, get_dashboard_data
from trail_manager import TrailManager
from wheel import (
    calculate_steering_wheel_quotas, compute_categories, format_allocation_report,
    apply_tree_weighting, record_category_id,
)
from risk_manager import (
    calc_metrics, composite_score, distribute_lots, check_integration_budget, lot_ceiling_money,
    check_daily_loss_limit, check_equity_stop, check_margin_level, realtime_quota_recalc,
    MAX_COMBOS_PER_STRATEGY,
    _sl_money_per_lot, _normalize_volume,
)
from strategy_engine import (
    write_ranking, sync_active_strategies, check_active_signals,
    send_order, close_order, get_deal_exit_price,
    strategy_key, assign_magic, _record_close,
    deduplicate_results, _short_name,
    write_active_state, get_non_usd
)

from strategies.stochastic import (
    calc_stochastic, backtest as backtest_stoch,
    check_entry as check_entry_stoch, check_exit as check_exit_stoch,
)
from strategies.parabolic import (
    calc_parabolic, backtest as backtest_parabolic,
    check_entry as check_entry_parabolic, check_exit as check_exit_parabolic,
)
from strategies.moving_average import (
    calc_moving_average, backtest as backtest_ma,
    check_entry as check_entry_ma, check_exit as check_exit_ma,
)
from strategies.macd_cross import (
    calc_macd_cross, backtest_macd_cross,
    check_entry as check_entry_macd_cross, check_exit as check_exit_macd_cross,
)
from strategies.rsi_reversal import (
    calc_rsi_reversal, backtest_rsi_reversal,
    check_entry as check_entry_rsi_reversal, check_exit as check_exit_rsi_reversal,
)
from strategies.bollinger_breakout import (
    calc_bollinger, backtest_bollinger,
    check_entry as check_entry_bollinger, check_exit as check_exit_bollinger,
)
from strategies.ema_crossover import (
    calc_ema_crossover, backtest_ema_crossover,
    check_entry as check_entry_ema_crossover, check_exit as check_exit_ema_crossover,
)
from strategies.rsi_divergence import (
    calc_rsi_divergence, backtest_rsi_divergence,
    check_entry as check_entry_rsi_divergence, check_exit as check_exit_rsi_divergence,
)
from strategies.ichimoku_cloud import (
    calc_ichimoku, backtest_ichimoku,
    check_entry as check_entry_ichimoku, check_exit as check_exit_ichimoku,
)
from strategies.random_forest import (
    calc_random_forest, backtest as backtest_rf,
    check_entry as check_entry_rf, check_exit as check_exit_rf,
)
from strategies.logreg import (
    calc_logreg, backtest as backtest_logreg,
    check_entry as check_entry_logreg, check_exit as check_exit_logreg,
)
from strategies.zscore_reversion import (
    calc_zscore, backtest as backtest_zscore,
    check_entry as check_entry_zscore, check_exit as check_exit_zscore,
)
from strategies.autocorrelation_momentum import (
    calc_autocorrelation, backtest as backtest_autocorr,
    check_entry as check_entry_autocorr, check_exit as check_exit_autocorr,
)
from strategies.hurst_regime_filter import (
    calc_hurst, backtest as backtest_hurst,
    check_entry as check_entry_hurst, check_exit as check_exit_hurst,
)
from strategies.linear_regression_channel import (
    calc_lr_channel, backtest as backtest_lrc,
    check_entry as check_entry_lrc, check_exit as check_exit_lrc,
)
from strategies.percentile_reversion import (
    calc_percentile, backtest as backtest_percentile,
    check_entry as check_entry_percentile, check_exit as check_exit_percentile,
)
from strategies.runs_test_trend import (
    calc_runs_test, backtest as backtest_runs,
    check_entry as check_entry_runs, check_exit as check_exit_runs,
)
from strategies.cointegration_pairs import (
    calc_cointegration, backtest as backtest_coint,
    check_entry as check_entry_coint, check_exit as check_exit_coint,
)
from strategies.rolling_sharpe_filter import (
    calc_rolling_sharpe, backtest as backtest_sharpe,
    check_entry as check_entry_sharpe, check_exit as check_exit_sharpe,
)
from strategies.skewness_extreme import (
    calc_skewness, backtest as backtest_skewness,
    check_entry as check_entry_skewness, check_exit as check_exit_skewness,
)
from strategies.bayesian_trend_update import (
    calc_bayesian_trend, backtest as backtest_bayesian,
    check_entry as check_entry_bayesian, check_exit as check_exit_bayesian,
)
from strategies.kurtosis_spike import (
    calc_kurtosis, backtest as backtest_kurtosis,
    check_entry as check_entry_kurtosis, check_exit as check_exit_kurtosis,
)
from strategies.chi_square_distribution import (
    calc_chi_square, backtest as backtest_chi_square,
    check_entry as check_entry_chi_square, check_exit as check_exit_chi_square,
)
from strategies.vwap_reversion import (
    calc_vwap, backtest as backtest_vwap,
    check_entry as check_entry_vwap, check_exit as check_exit_vwap,
)
from strategies.momentum_breakout import (
    calc_momentum, backtest as backtest_momentum,
    check_entry as check_entry_momentum, check_exit as check_exit_momentum,
)
from strategies.pin_bar_reversal import (
    calc_pin_bar, backtest as backtest_pin_bar,
    check_entry as check_entry_pin_bar, check_exit as check_exit_pin_bar,
)
from strategies.prev_daily_candle_direction import (
    calc_prev_daily_direction, backtest as backtest_prev_daily,
    check_entry as check_entry_prev_daily, check_exit as check_exit_prev_daily,
)
from strategies.rolling_correlation_momentum import (
    calc_rolling_correlation, backtest as backtest_corr,
    check_entry as check_entry_corr, check_exit as check_exit_corr,
)
from strategies.williams_r_extreme import (
    calc_williams_r, backtest as backtest_williams_r,
    check_entry as check_entry_williams_r, check_exit as check_exit_williams_r,
)
from strategies.macd_histogram_reversal import (
    calc_macd_histogram, backtest as backtest_macd_histogram,
    check_entry as check_entry_macd_histogram, check_exit as check_exit_macd_histogram,
)
from strategies.bb_squeeze_breakout import (
    calc_bb_squeeze, backtest as backtest_bb_squeeze,
    check_entry as check_entry_bb_squeeze, check_exit as check_exit_bb_squeeze,
)
from strategies.donchian_breakout import (
    calc_donchian, backtest as backtest_donchian,
    check_entry as check_entry_donchian, check_exit as check_exit_donchian,
)
from strategies.engulfing_pattern import (
    calc_engulfing, backtest as backtest_engulfing,
    check_entry as check_entry_engulfing, check_exit as check_exit_engulfing,
)
from strategies.cci_reversion import (
    calc_cci, backtest as backtest_cci,
    check_entry as check_entry_cci, check_exit as check_exit_cci,
)
from strategies.supertrend import (
    calc_supertrend, backtest as backtest_supertrend,
    check_entry as check_entry_supertrend, check_exit as check_exit_supertrend,
)
from strategies.adx_trend import (
    calc_adx, backtest as backtest_adx,
    check_entry as check_entry_adx, check_exit as check_exit_adx,
)
from strategies.obv_flow import (
    calc_obv, backtest as backtest_obv,
    check_entry as check_entry_obv, check_exit as check_exit_obv,
)
from strategies.morning_evening_star import (
    calc_morning_evening_star, backtest as backtest_morning_evening_star,
    check_entry as check_entry_morning_evening_star, check_exit as check_exit_morning_evening_star,
)
from data_loader import (
    symbol_data, load_h1, update_symbol_bar,
    load_journal, save_journal, record_trade,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_DIR = os.path.join(BASE_DIR, "journals")
JOURNAL_FILE = os.path.join(JOURNAL_DIR, f"journal_{datetime.now().strftime('%Y%m')}.csv")

COLUMNS = ['symbol', 'param_key', 'sl_points', 'tp_points',
           'entry_time', 'exit_time', 'direction',
           'entry_price', 'exit_price', 'lot', 'profit',
           'exit_reason', 'ticket']


# тХРтХРтХР ╨г╤В╨╕╨╗╨╕╤В╨░: ╨╖╨░╨┐╨╕╤Б╤М night_reset.json (╨┐╨╡╤А╨▓╤Л╨╣ ╨┐╤А╨╛╨│╨╛╨╜ + ╨║╨░╨╢╨┤╤Л╨╣ ╨╜╨╛╤З╨╜╨╛╨╣ ╨┐╨╡╤А╨╡╤А╨░╤Б╤З╤С╤В) тХРтХРтХР
def _write_night_reset(night_reset_path, start_time, symbols_count, results_count, ts=None):
    """Записывает night_reset.json — и при первом прогоне, и каждую ночь."""
    if ts is None:
        ts = datetime.now()
    # timestamp — РЕАЛЬНОЕ время записи маркера. Раньше сюда принудительно писали
    # 03:00 (fake_timestamp), и по маркеру нельзя было понять, когда прогон был на
    # самом деле: оставалось только гадать по времени перезапуска процесса.
    night_window = ts.replace(hour=3, minute=0, second=0, microsecond=0)
    with _safe_marker_write(night_reset_path, 'night_reset.json (main)') as f:
        json.dump({
            'started_at': start_time.isoformat(),
            'timestamp': ts.isoformat(),
            'night_window': night_window.isoformat(),
            'status': 'completed',
            'symbols': symbols_count,
            'total_results': results_count,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  ✅ Маркер прогона записан ({ts.strftime('%Y-%m-%d %H:%M')}, "
          f"ночное окно {night_window.strftime('%H:%M')}) — старт: {start_time}")


# тХРтХРтХР ╨г╤В╨╕╨╗╨╕╤В╨░: ╨╝╨░╤А╨║╨╡╤А ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╡╨│╨╛ ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ (╨┐╤А╨░╨▓╨╕╨╗╨╛ ┬л╨╜╨╡ ╤З╨░╤Й╨╡, ╤З╨╡╨╝ ╤А╨░╨╖ ╨▓ N ╨┤╨╜╨╡╨╣┬╗) тХРтХРтХР
def _read_last_full_recalc(marker_path):
    """Дата последнего ПОЛНОГО пересчёта — ТОЛЬКО из маркера last_full_recalc.json."""
    try:
        with open(marker_path, 'r', encoding='utf-8') as f:
            ts = json.load(f).get('last_full_recalc', '')
        if ts:
            return datetime.fromisoformat(ts).date()
    except (OSError, ValueError, json.JSONDecodeError):
        pass



    # Фолбэк (маркера ещё нет, напр. сразу после обновления): самая свежая дата из
    # night_reset.json и mtime чекпойнтов — чтобы НЕ запускать лишний ПОЛНЫЙ пересчёт.
    _dates = []
    try:
        # night_reset.json источником даты ПОЛНОГО пересчёта НЕ является: его перезаписывают
        # и ночные реранки (03:00 каждый день). Из-за этого «последний полный» выглядел как
        # сегодняшний, и первый полный пересчёт откладывался на сутки. Остаётся только
        # mtime чекпойнтов символов — их пишет реальный расчёт.
        with open(os.path.join(_checkpoint_dir(), '.night_reset_not_a_full_recalc_source'),
                  'r', encoding='utf-8') as _f2:
            _ts2 = json.load(_f2).get('timestamp', '')
        if _ts2:
            _dates.append(datetime.fromisoformat(_ts2).date())
    except (OSError, ValueError, json.JSONDecodeError):
        pass



    try:
        _ck = _checkpoint_dir()
        _skip2 = ('night_reset.json', 'last_run.json', 'last_full_recalc.json',
                  'full_recalc_inprogress.json')
        for _name in os.listdir(_ck):
            if _name.endswith('.json') and _name not in _skip2:
                _dates.append(datetime.fromtimestamp(os.path.getmtime(os.path.join(_ck, _name))).date())
    except OSError:
        pass



    # Дату ПОЛНОГО пересчёта берём ТОЛЬКО из маркера last_full_recalc.json.
    # mtime чекпойнтов и night_reset.json давали фальшивое «последний полный = сегодня»
    # и молча откладывали настоящий пересчёт на сутки. Нет маркера → дата неизвестна →
    # _full_recalc_due() считает пересчёт нужным.
    return None


def _full_recalc_due(now, marker_path, gap_days, is_first_run=False, daily=False):
    """Пора ли делать ПОЛНЫЙ пересчёт. Возвращает (due, days_since_full, last_full_date).

    Правило: один ПОЛНЫЙ пересчёт на «окно выходных» (Сб–Вс). Окно определяется по субботе:
    для Сб/Вс — текущее, для Пн–Пт — прошедшее. Если в окне ПОЛНОГО не было (уик-энд пропущен),
    догоняем при первом же запуске/ночном прогоне, но не раньше, чем через gap_days дней
    после прошлого ПОЛНОГО (защита от лишних повторов).
    """
    last_full_date = _read_last_full_recalc(marker_path)
    days_since = (now.date() - last_full_date).days if last_full_date else None
    if is_first_run or last_full_date is None:
        return True, days_since, last_full_date
    anchor = now.date() - timedelta(days=(now.weekday() - 5) % 7)  # суббота текущего/прошедшего окна
    in_window = last_full_date >= anchor
    gap_ok = (days_since is None) or (days_since >= gap_days)
    if daily:
        # full_recalc_daily=True: обновляем ВСЮ корзину каждую ночь — окно выходных
        # не учитываем, остаётся только защита от повторов (gap_days).
        return gap_ok, days_since, last_full_date
    return (not in_window) and gap_ok, days_since, last_full_date


def _has_open_positions(magic_min=770000, magic_max=869999):
    """Есть ли НАШИ открытые позиции (magic в боевом диапазоне).

    Нужно для решения о полном пересчёте: в синхронном режиме, пока он идёт (150–230 мин),
    не запущен, то есть бары, сигналы, трейлинг и аварийные защиты не проверяются.
    """
    try:
        positions = mt5.positions_get()
    except Exception:
        return False
    if not positions:
        return False
    for p in positions:
        try:
            m = int(getattr(p, 'magic', 0) or 0)
        except (TypeError, ValueError):
            continue
        if magic_min <= m <= magic_max:
            return True
    return False


def _in_full_window(now, end_hour=10, start_hour=3):
    """Допустим ли ПОЛНЫЙ пересчёт сейчас: выходные — всегда, будни — только в ночном окне.

    Днём полный проход (150–230 мин) заблокировал бы боевой цикл на самое активное
    время, поэтому дневные старты идут по чекпойнтам, а обновление уходит в ночь.
    """
    if now.weekday() >= 5:
        return True
    return start_hour <= now.hour < end_hour


def _write_full_recalc_marker(marker_path, ts=None):
    """Фиксирует дату последнего ПОЛНОГО пересчёта. Реранк по чекпойнтам этот файл не перезаписывает."""
    if ts is None:
        ts = datetime.now()
    with _safe_marker_write(marker_path, 'last_full_recalc.json') as f:
        json.dump({'last_full_recalc': ts.isoformat()}, f, ensure_ascii=False, indent=2)


# тХРтХРтХР ╨д╨╛╨╜╨╛╨▓╤Л╨╣ (async) ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В тХРтХРтХР
# Полный проход (150–230 мин) исторически держал боевой цикл закрытым: бары не
# опрашивались, сигналы не рождались, трейлинг и аварийные защиты (daily loss,
# equity stop, margin) не срабатывали. Теперь тяжёлая часть считается в отдельном
# потоке (backtest_job.BacktestJob), цикл живёт обычной жизнью, а результат
# применяется по завершении job — повторным входом в ночной блок (реранк по чекпойнтам):
# job пишет чекпойнты сам, поэтому передавать результаты «в руки» не нужно.
_bg_job = None       # активный BacktestJob (одновременно не более одного)
_bg_ready = False    # завершённый job ждёт применения (чекпойнты уже свежие)
_bg_failed = None    # текст ошибки завершившегося с ошибкой job (для лога)
_bg_elapsed_min = 0.0


def _bg_running():
    """Идёт ли фоновый пересчёт прямо сейчас."""
    return _bg_job is not None and _bg_job.running()


def _bg_start(symbols, symbol_data, strategy_params, bt_cfg):
    """Поставить фоновый ПОЛНЫЙ пересчёт. Возвращает job."""
    global _bg_job, _bg_ready, _bg_failed
    from backtest_job import BacktestJob
    _bg_ready = False
    _bg_failed = None
    _bg_job = BacktestJob(symbols, symbol_data, strategy_params, bt_cfg,
                          force_recalc=True, is_night_run=True).start()
    return _bg_job


def _bg_poll():
    """Опросить фоновый пересчёт. True — job завершился (смотри _bg_ready/_bg_failed).

    Завершённый job «съедается»: ссылка сбрасывается, чтобы следующей ночью можно
    было поставить новый, а исход фиксируется в _bg_ready / _bg_failed.
    """
    global _bg_job, _bg_ready, _bg_failed, _bg_elapsed_min
    if _bg_job is None or _bg_job.running():
        return False
    _bg_elapsed_min = _bg_job.elapsed_min()
    if _bg_job.ok():
        _bg_ready = True
        _bg_failed = None
    else:
        _bg_ready = False
        _bg_failed = _bg_job.error()
    _bg_job = None
    return True


# тХРтХРтХР ╨д╨╛╨╜╨╛╨▓╤Л╨╣ ╨┤╨╛╨▒╨╛╤А ╤Б╨┤╨╡╨╗╨╛╨║ ╨▓ trades_db (╨╜╨╡ ╨▒╨╗╨╛╨║╨╕╤А╤Г╨╡╤В ╤В╨╛╤А╨│╨╛╨▓╤Л╨╣ ╤Ж╨╕╨║╨╗) тХРтХРтХР
_ingest_thread = None    # живой поток добора (None — свободно)
_ingest_error = None     # repr последней ошибки фонового добора (для лога)


def _ingest_start(days=1, verbose=False):
    """Запустить добор сделок в trades_db в отдельном демон-потоке.

    Зачем: mt5.history_deals_get + запись в SQLite могут занимать от секунд до
    минут (широкое окно, конкуренция за файл БД). В главном цикле это задерживало
    опрос баров, сигналы, трейлинг и аварийные защиты — поэтому добор вынесен
    из блокирующего участка: цикл ставит задачу и идёт дальше.

    Одновременно живёт не более одного добора. Поток-демон: умирает с процессом,
    торговлю не трогает. Ошибки не летят в вызывающий код, а копятся в
    _ingest_error (печатается при следующем запуске добора).
    """
    global _ingest_thread, _ingest_error
    if _ingest_thread is not None and _ingest_thread.is_alive():
        return False
    _ingest_error = None

    def _run():
        global _ingest_error
        try:
            import trades_db
            trades_db.ingest(days=days, verbose=verbose)
        except Exception as exc:   # fail-safe: БД не должна ронять пайплайн
            _ingest_error = repr(exc)

    import threading
    _ingest_thread = threading.Thread(target=_run, name='trades_db_ingest', daemon=True)
    _ingest_thread.start()
    return True


# тХРтХРтХР ╨б╤В╨░╤В╤Г╤Б ╤Б╨╡╨╝╨╡╨╣╤Б╤В╨▓ ╨▓ ╨С╨Ф (╤В╨░╨▒╨╗╨╕╤Ж╨░ family_status, journals/trades.db) тХРтХРтХР
def _record_family_status(all_results, active, run_kind=None):
    """Снапшот family_status — строго ПОСЛЕ реранка (после sync_active_strategies).

    Отвечает на вопрос «какие семейства полностью участвуют в ночных рэнкингах и
    готовы к торговле». Это ПЕРЕЗАПИСЬ состояния, а не лог: одна строка на
    (symbol, family), ответ одним SELECT по ключу. История «когда вошло/вышло»
    живёт в first_ready_at/last_ready_at + журнал переходов family_status_log.

    run_kind — режим прогона (full/incremental/partial/none); по умолчанию
    берётся из functions.LAST_RUN_KIND (его выставляет run_full_backtest).
    Fail-safe: любая ошибка гасится, цикл и торговлю не трогает.
    """
    try:
        import trades_db
        if run_kind is None:
            try:
                import functions as _fn
                run_kind = getattr(_fn, 'LAST_RUN_KIND', None) or 'none'
            except Exception:
                run_kind = 'none'
        rows = family_status_rows(
            bt_cfg.symbols, all_results, active, active_strategies,
            plan_by_family=strategy_combos_per_symbol(strategy_params),
            min_score=risk_cfg.min_score,
            run_kind=run_kind,
            key_fn=strategy_key,
        )
        trades_db.record_family_status(rows)
        # Score ВСЕХ семейств (включая те, что целиком ниже порога): источник —
        # чекпойнты символов, а не all_results. Нужен для колонки score в Roadmap:
        # оценка должна быть видна всегда, даже супер низкая.
        from functions import family_score_rows as _fs_rows
        trades_db.record_family_scores(
            _fs_rows(bt_cfg.symbols, risk_cfg.min_score, run_kind))
    except Exception as exc:
        print(f"  [WARN] family_status: {exc!r}", flush=True)


# тХРтХРтХР ╨г╤В╨╕╨╗╨╕╤В╨░: ╨┤╨╕╨░╨│╨╜╨╛╤Б╤В╨╕╨║╨░ тАФ ╤З╤В╨╛ ╨║╨╛╨┤ ┬л╨▓╨╕╨┤╨╕╤В┬╗ ╨┐╨╛ ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╕╨╝ ╤А╨░╤Б╤З╤С╤В╨░╨╝ тХРтХРтХР
def _file_info(path):
    """(exists, mtime_str, первые 400 символов содержимого) — для диагностики."""
    try:
        if not os.path.exists(path):
            return False, '-', '(файла нет)'
        mt = datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')
        with open(path, 'r', encoding='utf-8') as f:
            txt = f.read(400)
        return True, mt, txt.replace('\n', ' ').strip()
    except (OSError, ValueError):
        return False, '-', '(не читается)'


def _log_recalc_chain(now, night_reset_path, marker_path, is_first_run, gap_days,
                      days_since_full, weekend_full_due, manual_full):
    """Краткий вывод: включаем ли ПОЛНЫЙ пересчёт и по какой причине (триггер в скобках).
    Подробная цепочка (файлы/mtime/чекпойнты) печатается только при FULL_RECALC_DEBUG=True."""
    if weekend_full_due:
        _trg = 'первый запуск — чекпойнтов нет' if is_first_run else \
               f'окно выходных / догон (последний ПОЛНЫЙ {days_since_full} дн. назад, порог {gap_days} дн.)'
        print(f"  🔁 ПОЛНЫЙ пересчёт: ДА ({_trg})")
    else:
        _last_txt = 'тАФ'
        try:
            with open(marker_path, 'r', encoding='utf-8') as _f:
                _ts = json.load(_f).get('last_full_recalc', '')
            if _ts:
                _last_txt = datetime.fromisoformat(_ts).strftime('%d.%m.%y %H:%M')
        except (OSError, ValueError, json.JSONDecodeError):
            pass



        print(f"  🔁 ПОЛНЫЙ пересчёт: НЕТ (последний был {_last_txt}; порог {gap_days} дн. — окно выходных закрыто)")
    if not globals().get('FULL_RECALC_DEBUG', False):
        return
    ckpt_dir = _checkpoint_dir()
    sym_files = []
    try:
        skip = ('night_reset.json', 'last_run.json', 'last_full_recalc.json')
        sym_files = [f for f in os.listdir(ckpt_dir) if f.endswith('.json') and f not in skip]
    except OSError:
        pass



    last_sym_mtime = '-'
    if sym_files:
        try:
            newest = max(os.path.getmtime(os.path.join(ckpt_dir, f)) for f in sym_files)
            last_sym_mtime = datetime.fromtimestamp(newest).strftime('%Y-%m-%d %H:%M:%S')
        except (OSError, ValueError):
            pass




    nr_e, nr_m, nr_c = _file_info(night_reset_path)
    mk_e, mk_m, mk_c = _file_info(marker_path)
    lr_e, lr_m, lr_c = _file_info(os.path.join(ckpt_dir, 'last_run.json'))

    print("\n" + "тХР" * 66)
    print("  ДИАГНОСТИКА РАСЧЁТОВ — что видит код на старте")
    print("тХР" * 66)
    print(f"  Время:              {now.strftime('%Y-%m-%d %H:%M:%S')} ({now.strftime('%A')}, weekday={now.weekday()})")
    print(f"  Рабочая папка:      {os.getcwd()}")
    print(f"  Папка чекпойнтов:   {ckpt_dir}")
    print(f"  Авто-полный на выходных: ВКЛ, порог gap = {gap_days} дн.")
    print(f"  night_reset.json:       exists={nr_e} | mtime={nr_m}")
    print(f"      ↳ {nr_c}")
    print(f"  last_full_recalc.json:  exists={mk_e} | mtime={mk_m}")
    print(f"      ↳ {mk_c}")
    print(f"  last_run.json:          exists={lr_e} | mtime={lr_m}")
    print(f"      ↳ {lr_c}")
    print(f"  Чекпойнты символов: {len(sym_files)} шт | последний изменён: {last_sym_mtime}")
    print("  тФАтФА ╤А╨╡╤И╨╡╨╜╨╕╨╡ тФАтФА")
    print(f"  is_first_run={is_first_run} | дней с последнего ПОЛНОГО = {days_since_full} | weekend_full_due={weekend_full_due}")
    if weekend_full_due or now.weekday() >= 5:
        if weekend_full_due:
            print("  → ПОЛНЫЙ пересчёт ЗАПУСКАЕМ (окно выходных / догон)")
        else:
            print("  → ПОЛНЫЙ пересчёт НЕ запускаем — реранк по чекпойнтам")
    else:
        print("  → Будний день: реранк по чекпойнтам (сетку не пересчитываем)")
    print("тХР" * 66 + "\n")


# тХРтХРтХР ╨и╨в╨г╨а╨Т╨Р╨Ы (╨Ю╨С╨п╨Ч╨Р╨в╨Х╨Ы╨м╨Э╨л╨Щ ╤И╨░╨│ ╨┐╨░╨╣╨┐╨╗╨░╨╣╨╜╨░) тХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХР
def run_steering_wheel(active_strategies, active, symbol_data, balance,
                       risk_cfg, steering_cfg, journal_dir=None, tag=''):
    """Пересчёт квот по категориям symbol+family и перекладка лотов по реальным сделкам.

    ОБЯЗАТЕЛЬНЫЙ шаг: вызывается при старте, сразу после ночного пересчёта и далее
    каждые steering_cfg.interval_sec — независимо от того, был ли бэктест.
    Раньше блок жил внутри ветки бэктеста и внутри `if metrics:`, поэтому штурвал
    молча пропускался, если в окне не было сделок. Теперь любая причина пропуска
    печатается в лог: нет метрик → берём сохранённые квоты; нет квоты у категории,
    sl_money<=0, бюджет<=0, открытая позиция — считаются отдельно.

    Возвращает dict со счётчиками (changed/synced/no_quota/bad_sl/no_budget/
    with_position/unchanged/categories/source). Исключения не пробрасываются:
    пайплайн не должен падать из-за штурвала, но ошибка печатается как [ERROR].
    """
    journal_dir = journal_dir or JOURNAL_DIR
    st = {'changed': 0, 'synced': 0, 'no_quota': 0, 'bad_sl': 0, 'no_budget': 0,
          'killed': 0, 'tilt': {},
          'with_position': 0, 'unchanged': 0, 'categories': 0, 'source': 'none'}
    # st: счётчики прогона (killed — сколько стратегий остановил kill switch)
    _tag = f" {tag}" if tag else ''
    print(f"\n  [STEERING] Старт{_tag}: {len(active_strategies or {})} стратегий, "
          f"окно {steering_cfg.lookback_days} дн., баланс {balance:,.0f} ₽", flush=True)

    try:
        quotas_path = os.path.join(journal_dir, steering_cfg.quotas_file)
        prev_quotas = {}
        if os.path.exists(quotas_path):
            try:
                with open(quotas_path, 'r', encoding='utf-8') as _qf:
                    prev_quotas = json.load(_qf) or {}
            except Exception as _qe:
                print(f"  [ERROR] Штурвал: {quotas_path} не читается ({_qe!r}) — "
                      f"считаем квоты с нуля", flush=True)
                prev_quotas = {}

        # тФАтФА ╨Ш╤Б╤В╨╛╤З╨╜╨╕╨║: Strategy Tree (╨╛╨║╨╜╨╛ lookback_days), ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ symbol+family тФАтФА
        # Та же выборка сделок, что в дереве/штурвале дэшборда: числа совпадают 1-в-1.
        metrics = []
        try:
            _alloc = get_dashboard_data(steering_cfg.lookback_days, manage_connection=False)
            _adeals = _alloc.get('trades_df') if _alloc else None
            metrics = compute_categories(_adeals) if _adeals is not None else []
        except Exception as _de:
            print(f"  [ERROR] Штурвал: Strategy Tree недоступен ({_de!r}) — "
                  f"работаем на сохранённых квотах", flush=True)

        new_quotas = dict(prev_quotas)
        if metrics:
            new_quotas = calculate_steering_wheel_quotas(
                metrics,
                prev_quotas,
                {
                    'alpha': steering_cfg.alpha,
                    'min_q': steering_cfg.min_q,
                    'max_q': steering_cfg.max_q,
                    'score_mode': steering_cfg.score_mode,
                    'min_trades': steering_cfg.min_trades,
                    'gamma': getattr(steering_cfg, 'gamma', 1.5),
                    'score_volume_prior': getattr(steering_cfg, 'score_volume_prior', 0.0),
                    # Политика потерь (kill switch): порог в рублях, рублёвая риск-квота
                    'quota_rub': balance * risk_cfg.max_risk_pct,
                    'loss_decay': getattr(steering_cfg, 'loss_decay', 0.25),
                    'kill_pnl_pct': getattr(steering_cfg, 'kill_pnl_pct', 0.02),
                    'kill_pnl_rub': getattr(steering_cfg, 'kill_pnl_rub', 0.0),
                    'kill_min_trades': getattr(steering_cfg, 'kill_min_trades', 3),
                },
                # Категории активного плана — даже без сделок в окне должны получить
                # ключ в файле квот, иначе штурвал не может тронуть их лот.
                known_ids=sorted({_cid for _cid in (record_category_id(_s)
                                                    for _s in (active_strategies or {}).values())
                                  if _cid}),
            )
            with open(quotas_path, 'w', encoding='utf-8') as _qf:
                json.dump(new_quotas, _qf, ensure_ascii=False, indent=2)

            # тФАтФА ╨Я╤А╨╕╨╜╤В: Strategy Tree тЖТ ╨┐╨╡╤А╨╡╨║╨╗╨░╨┤╨║╨░ ╨╛╨▒╤К╤С╨╝╨░ тФАтФА
            print(f"\n  [WHEEL] Пересчёт квот (score_mode={steering_cfg.score_mode}) "
                  f"(окно {steering_cfg.lookback_days} дн.).", flush=True)
            for _line in format_allocation_report(
                    metrics, prev_quotas, new_quotas,
                    steering_cfg.lookback_days,
                    min_trades=steering_cfg.min_trades,
                    score_mode=steering_cfg.score_mode):
                print(_line, flush=True)
            st['source'] = 'tree'
        else:
            print(f"  [WHEEL] Свежих сделок за {steering_cfg.lookback_days} дн. нет — "
                  f"перекладка по сохранённым квотам: {len(new_quotas)} категорий "
                  f"({steering_cfg.quotas_file})", flush=True)
            st['source'] = 'saved'

        st['categories'] = len(new_quotas)
        if not new_quotas:
            print("  [ERROR] Штурвал: квот нет вообще (нет ни метрик Strategy Tree, ни файла "
                  f"{steering_cfg.quotas_file}) — лоты не тронуты", flush=True)
            return st

        # тФАтФА ╨Я╨╡╤А╨╡╨║╨╗╨░╨┤╨║╨░ ╨╗╨╛╤В╨╛╨▓: ╨Р╨С╨б╨Ю╨Ы╨о╨в╨Э╨л╨Щ ╤Ж╨╡╨╗╨╡╨▓╨╛╨╣ ╨╗╨╛╤В тФАтФА
        #     lot_i = (budget × q_i / Σq_covered) × (score_i / Σscore_категории) / sl_money_i
        # budget — свободная часть риск-квоты (за вычетом риска открытых позиций),
        # поэтому Σ(lot×sl_money) ≤ quota по построению.
        risk_quota = balance * risk_cfg.max_risk_pct
        _slm = {}
        _used_risk = 0.0
        _free_keys = []
        _n_in_cat = {}
        _score_sum_cat = {}
        _sid_by_key = {}
        for _k, _s in active_strategies.items():
            _info = symbol_data.get(_s['symbol'], {}).get('info')
            _m = _sl_money_per_lot(_s['symbol'], _info, _s.get('sl_points') or 0)
            _slm[_k] = _m
            _sid_by_key[_k] = record_category_id(_s)
            if _s['position'] is not None:
                _used_risk += float(_s['lot']) * _m
                st['with_position'] += 1
            else:
                _free_keys.append(_k)
                _sid = _sid_by_key[_k]
                _n_in_cat[_sid] = _n_in_cat.get(_sid, 0) + 1
                _score_sum_cat[_sid] = (_score_sum_cat.get(_sid, 0.0)
                                        + max(float(_s.get('score') or 0.0), 0.0))

        _free_sids = {_sid_by_key[_k] for _k in _free_keys} - {None}
        _free_sids = {_sid_by_key[_k] for _k in _free_keys} - {None}
        # Бюджет делим на ВСЕ категории с ненулевой квотой, а не только на
        # свободные: иначе свободная стратегия с квотой-полом (1.04%) забирала
        # весь незанятый бюджет и получала риск в 1.8× от номинала
        # (17.10: EURUSDrf_pin_bar — 4,003 ₽ вместо 2,214 ₽).
        # Budget is split only over categories that really receive lots (the plan).
        # Old formula summed ALL quotas from the file (~0.675) while plan categories
        # hold ~0.16, so only ~24% of the budget reached lots (quota used ~33%).
        _q_covered = sum(v for sid, v in new_quotas.items() if v > 0 and sid in _free_sids)
        if _q_covered <= 0:
            _q_covered = sum(v for v in new_quotas.values() if v > 0)
        _budget = max(0.0, risk_quota - _used_risk)
        print(f"  [STEERING] Свободных {len(_free_keys)} | в позициях {st['with_position']} | "
              f"риск позиций {_used_risk:,.0f} ₽ | бюджет {_budget:,.0f} ₽ из "
              f"{risk_quota:,.0f} ₽ | Σq всех категорий {_q_covered:.3f}", flush=True)
        if _budget <= 0:
            print("  [ERROR] Штурвал: свободного бюджета нет (квота занята открытыми "
                  "позициями) — лоты не переложены", flush=True)
            st['no_budget'] = len(_free_keys)
            return st

        for key, s in active_strategies.items():
            if s['position'] is not None:
                continue
            sid = record_category_id(s)
            # Снять тильт прошлого цикла: считаем и сравниваем с ЛОТОМ-БАЗИСОМ,
            # иначе штурвал каждый час «находит» изменение там, где лот просто
            # несёт надбавку ±20% (тильт применится заново в конце этой функции).
            _tb, _tm = s.get('tilt_base'), s.get('tilt_mult')
            if _tb is not None and _tm is not None:
                _expect = round(max(float(_tb) * float(_tm), risk_cfg.min_lot), 2)
                if abs(float(s.get('lot') or 0.0) - _expect) <= 1e-9:
                    s['lot'] = float(_tb)
                s.pop('tilt_base', None)
                s.pop('tilt_mult', None)
            q_new = new_quotas.get(sid) if sid else None
            if q_new is None:
                st['no_quota'] += 1
                print(f"  [WARN] Штурвал: {key} — нет квоты для категории {sid!r}, "
                      f"лот не тронут", flush=True)
                continue
            _m = _slm.get(key, 0.0)
            if q_new <= 0:
                # Kill switch: категория убыточна (квота 0) → новые входы запрещены.
                if s.get('enabled', True) or float(s.get('lot') or 0) > 0:
                    print(f"  [WHEEL] KILL {key}: q=0 → торговля остановлена "
                          f"(категория {sid}, лот {s['lot']:.3f} → 0)", flush=True)
                s['lot'] = 0.0
                s['enabled'] = False
                s['disabled_reason'] = f'steering: квота категории {sid} = 0 (живой убыток)'
                st['killed'] += 1
                continue
            if s.get('enabled', True) is False:
                print(f"  [WHEEL] возврат в работу: {key} (категория {sid} снова в плюсе)", flush=True)
                s['enabled'] = True
                s.pop('disabled_reason', None)
            _m = _slm.get(key, 0.0)
            if _m <= 0 or _q_covered <= 0:
                st['bad_sl'] += 1
                print(f"  [WARN] Штурвал: {key} — sl_money={_m:,.2f} или Σq={_q_covered:.3f}, "
                      f"лот не тронут", flush=True)
                continue
            # Доля внутри категории — по score бэктеста (как в tree_weighted_lots);
            # поровну — только если Σscore категории = 0.
            _sc = max(float(s.get('score') or 0.0), 0.0)
            _scat = _score_sum_cat.get(sid, 0.0)
            _share = (_sc / _scat) if _scat > 0 else (1.0 / max(1, _n_in_cat.get(sid, 1)))
            new_lot = _budget * (q_new / _q_covered) * _share / _m
            _info = symbol_data.get(s['symbol'], {}).get('info')
            _vol = _normalize_volume(new_lot, _info)
            new_lot = max(_vol if _vol is not None else risk_cfg.min_lot, risk_cfg.min_lot)




            # Ceiling for one strategy: a money rule on the balance, so a single
            # JPY strategy can never take a whole lot of a 1M deposit.
            _max_lot = lot_ceiling_money(symbol=s['symbol'], info=_info,
                                         sl_points=s.get('sl_points'),
                                         balance=balance, sl_money=_m)
            if _max_lot > 0 and new_lot > _max_lot:
                new_lot = _max_lot
            if abs(new_lot - s['lot']) > 1e-9:
                print(f"  [STEERING] {key}: lot {s['lot']:.3f} -> {new_lot:.3f} "
                      f"(q {q_new:.3f}, score {_sc:.2f}/{_scat:.2f}, риск "
                      f"{s['lot'] * _m:,.0f} -> {new_lot * _m:,.0f} ₽)")
                s['lot'] = new_lot
                st['changed'] += 1
            else:
                st['unchanged'] += 1

        # тФАтФА ╨Я╤А╨╡╨╝╨╕╤П/╨┤╨╕╤Б╨║╨╛╨╜╤В ╨┐╨╛ ╤В╨░╨║╤В╨╕╨║╨╡ ╨▓╤Е╨╛╨┤╨░ (┬▒20% ╨║ ╨╛╨▒╤К╤С╨╝╤Г): ╨б╨Р╨Ь╨л╨Щ ╨Ъ╨Ю╨Э╨Х╨ж ╤А╨╡╤А╨░╨╜╨║╨░ тФАтФА
        # Объём уже переложен штурвалом — здесь он только масштабируется по лучшей/
        # худшей связке «пара + день выхода» за окно до 90 дней (tactic_tilt.py).
        # Идемпотентно: повторный вызов с тем же множителем второй раз ±20% не
        # начисляет (маркеры tilt_base/tilt_mult), а лот от штурвала — новый базис.
        try:
            import tactic_tilt as _tt
            if getattr(steering_cfg, 'tactic_tilt_enabled', True):
                st['tilt'] = _tt.apply_tactic_tilt(
                    list(active_strategies.values()), when=datetime.now(),
                    pct=getattr(steering_cfg, 'tactic_tilt_pct', 0.20),
                    window_days=getattr(steering_cfg, 'tactic_tilt_window_days', 90),
                    min_trades=getattr(steering_cfg, 'tactic_tilt_min_trades', 2),
                    weekday_only=getattr(steering_cfg, 'tactic_tilt_weekday_only', False),
                    min_lot=risk_cfg.min_lot, log=print)
                if st['tilt'].get('n_changed'):
                    st['changed'] += int(st['tilt']['n_changed'])
        except Exception as _tt_e:
            print(f"  [WARN] TILT: {_tt_e!r}", flush=True)

        # тФАтФА ╨г╨╜╨╕╤Д╨╕╨║╨░╤Ж╨╕╤П ╨╕╤Б╤В╨╛╤З╨╜╨╕╨║╨░ ╨╗╨╛╤В╨░ тФАтФА
        # Штурвал правит active_strategies — это и есть бой. Переносим итог обратно
        # в план (active), чтобы active_state.json/дэшборд показывали реальную
        # перекладку, а не дотюненный tree-weighting лот. После этого active == active_strategies.
        # Tilt may lift a lot 20% above the ceiling - trim before it reaches the plan.
        _q_sync = float(risk_quota or 0.0)
        if _q_sync > 0:
            for _sk, _sv in active_strategies.items():
                _cap_sv = lot_ceiling_money(
                    symbol=_sv.get('symbol'),
                    info=symbol_data.get(_sv.get('symbol'), {}).get('info'),
                    sl_points=_sv.get('sl_points'),
                    balance=balance, sl_money=_slm.get(_sk, 0.0))
                if _cap_sv > 0 and float(_sv.get('lot') or 0) > _cap_sv:
                    _sv['lot'] = _cap_sv
        _lot_by_key = {_k: _v.get('lot') for _k, _v in active_strategies.items()}
        for _r in (active or []):
            _rk = strategy_key(_r['symbol'], _r['param_key'],
                               _r.get('type', 'stoch'),
                               _r.get('parabolic_max'))
            _nl = _lot_by_key.get(_rk)
            if _nl is not None and abs(float(_nl) - float(_r.get('lot') or 0)) > 1e-9:
                _r['lot'] = _nl
                st['synced'] += 1

        print(f"  [STEERING] Итог: категорий {st['categories']} (источник: {st['source']}), "
              f"переложено {st['changed']}, без изменений {st['unchanged']}, "
              f"синхронизировано в план {st['synced']} | пропуски: в позиции "
              f"{st['with_position']}, нет квоты {st['no_quota']}, sl_money/Σq "
              f"{st['bad_sl']}, бюджет {st['no_budget']}", flush=True)
        if st['killed']:
            print(f"  [STEERING] Kill switch: {st['killed']} стратегий остановлено "
                  f"(квота категории = 0) — новые входы по ним запрещены", flush=True)
        return st

    except Exception as se:
        print(f"  [ERROR] Штурвал: {se!r} — квоты/лоты не изменены", flush=True)
        return st


if __name__ == '__main__':
    start_time = datetime.now()
    print(f"🚀 ЗАПУСК СИСТЕМЫ: {start_time.strftime('%H:%M:%S')}")

    # тХРтХРтХР ╨Ъ╨Ю╨Э╨д╨Ш╨У╨г╨а╨Р╨ж╨Ш╨п (╨╡╨┤╨╕╨╜╤Л╨╣ ╨╕╤Б╤В╨╛╤З╨╜╨╕╨║ тАФ config.py) тХРтХРтХР
    from config import build_default_configs
    app = build_default_configs()
    strategy_params = app.strategy_params
    bt_cfg = app.backtest_config
    risk_cfg = app.risk_params
    trail_cfg = app.trail_params
    steering_cfg = app.steering_params
    trail_mgr = TrailManager(trail_cfg)
    print(f"[TRAIL] {'ВКЛЮЧЁН' if trail_cfg.enabled else 'ВЫКЛЮЧЕН'} | "
          f"ATR(D1,{trail_cfg.atr_period}) x {trail_cfg.atr_multiplier} | "
          f"интервал {trail_cfg.check_interval_sec}с | мин.сдвиг {trail_cfg.min_move_points} пт")

    # тХРтХРтХР ╨Т╨л╨з╨Ш╨б╨Ы╨Ш╨в╨Х╨Ы╨м╨Э╨л╨Щ ╨С╨о╨Ф╨Ц╨Х╨в тХРтХРтХР
    def _combo(*args):
        result = 1
        for a in args:
            result *= a
        return result

    sp = strategy_params
    # Единый счёт комбинаций на 1 символ (легаси + реестр) — источник: functions.strategy_combos_per_symbol.
    # Раньше здесь был свой литерал (9018) без 10 семейств и без батча реестра → расходился с бэктестом.
    from functions import strategy_combos_per_symbol, STRATEGY_COMBO_LABELS
    integration_budgets_dict = {
        STRATEGY_COMBO_LABELS.get(k, k): v
        for k, v in strategy_combos_per_symbol(sp).items()
    }
    if False:  # legacy-литерал ниже (не используется); можно удалить вручную
        _legacy_budgets = {
        'Stoch':          _combo(len(sp.k_periods), len(sp.sl_points_list), len(sp.tp_points_list)),
        'Parabolic':      _combo(len(sp.parabolic_steps), len(sp.parabolic_maxs), len(sp.sl_points_list), len(sp.tp_points_list)),
        'MA':             _combo(len(sp.ma_periods), len(sp.sl_points_list), len(sp.tp_points_list)),
        'RandomForest':   _combo(len(sp.rf_lookbacks), len(sp.rf_nbars), len(sp.rf_thresholds), len(sp.sl_points_list), len(sp.tp_points_list)),
        'LogReg':         _combo(len(sp.logreg_lookbacks), len(sp.logreg_nbars), len(sp.logreg_thresholds), len(sp.sl_points_list), len(sp.tp_points_list)),
        'MACD-Cross':     _combo(len(sp.macd_cross_fast_list), len(sp.macd_cross_slow_list), len(sp.macd_cross_signal_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'RSI-Rev':        _combo(len(sp.rsi_rev_period_list), len(sp.rsi_rev_oversold_list), len(sp.rsi_rev_overbought_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'Bollinger':      _combo(len(sp.bb_period_list), len(sp.bb_std_list), len(sp.volume_period_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'EMA':            _combo(len(sp.ema_fast_list), len(sp.ema_slow_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'RSI-Div':        _combo(len(sp.rsi_div_period_list), len(sp.rsi_div_lookback_list), len(sp.rsi_div_threshold_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'Ichimoku':       _combo(len(sp.tenkan_list), len(sp.kijun_list), len(sp.senkou_b_list), len(sp.displacement_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'Zscore':         _combo(len(sp.zscore_sma_period_list), len(sp.zscore_threshold_list), len(sp.zscore_vol_period_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'Autocorr':       _combo(len(sp.autocorr_lag_list), len(sp.autocorr_threshold_list), len(sp.autocorr_vol_period_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'Hurst':          _combo(len(sp.hurst_window_list), len(sp.hurst_trend_threshold_list), len(sp.hurst_vol_period_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'LRC': _combo(len(sp.lrc_period_list), len(sp.lrc_std_threshold_list), len(sp.lrc_vol_period_list),
                      len(sp.sl_points_list), len(sp.tp_points_list)),
        'Percentile': _combo(len(sp.pct_period_list), len(sp.pct_low_list), len(sp.pct_high_list),
                             len(sp.pct_vol_period_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'Runs': _combo(len(sp.runs_window_list), len(sp.runs_threshold_list), len(sp.runs_vol_period_list),
                       len(sp.sl_points_list), len(sp.tp_points_list)),
        'Coint': _combo(len(sp.coint_window_list), len(sp.coint_threshold_list), len(sp.coint_beta_period_list),
                        len(sp.sl_points_list), len(sp.tp_points_list)),
        'Sharpe': _combo(len(sp.sharpe_window_list), len(sp.sharpe_threshold_list), len(sp.sharpe_vol_period_list),
                         len(sp.sl_points_list), len(sp.tp_points_list)),
        'Skewness': _combo(len(sp.skew_window_list), len(sp.skew_threshold_list), len(sp.skew_vol_period_list),
                           len(sp.sl_points_list), len(sp.tp_points_list)),
        'Kurtosis': _combo(len(sp.kurt_window_list), len(sp.kurt_threshold_list), len(sp.kurt_vol_period_list),
                           len(sp.sl_points_list), len(sp.tp_points_list)),
        'Bayesian':       _combo(len(sp.bayes_window_list), len(sp.bayes_threshold_list), len(sp.bayes_prior_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'ChiSq': _combo(len(sp.chisq_window_list), len(sp.chisq_entry_list), len(sp.chisq_exit_list),
                        len(sp.chisq_vol_period_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'VWAP': _combo(len(sp.vwap_vol_period_list), len(sp.vwap_std_mult_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'Momentum': _combo(len(sp.momentum_period_list), len(sp.momentum_threshold_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'PinBar': _combo(len(sp.pin_bar_body_ratio_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'PrevDaily': _combo(len(sp.prev_daily_hold_bars_list), len(sp.sl_points_list), len(sp.tp_points_list)),
        'CorrMomentum': _combo(len(sp.corr_window_list), len(sp.corr_threshold_list), len(sp.sl_points_list), len(sp.tp_points_list)),

    }

    budget_results = check_integration_budget(integration_budgets_dict, app.symbols)

    print("Боевой режим: все стратегии, полный перебор")

    # тХРтХРтХР ╨Я╨Ю╨Ф╨Ъ╨Ы╨о╨з╨Х╨Э╨Ш╨Х тХРтХРтХР
    terminal_on('demo')
    os.makedirs(JOURNAL_DIR, exist_ok=True)

    # тХРтХРтХР ╨Ч╨Р╨У╨а╨г╨Ч╨Ъ╨Р ╨Ш╨б╨в╨Ю╨а╨Ш╨Ш тХРтХРтХР
    print("Загрузка истории...")

    loaded_symbols = []
    failed_symbols = []

    for sym in bt_cfg.symbols:
        h1 = load_h1(sym)
        if h1 is None or len(h1) < 30:
            failed_symbols.append(sym)
            continue

        # symbol_select нужен только если дальше будет работа через MT5 API
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)

        if info is None:
            print(f"  ⚠ {sym}: symbol_info вернул None — бэктест/live по символу пропущен", flush=True)
            failed_symbols.append(sym)
            continue

        symbol_data[sym] = {
            'df_h1': h1,
            'current_hour': (h1.index[-1] + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0),
            'forming_bar': None,
            'info': info,
        }
        loaded_symbols.append(sym)

    # ИТОГОВАЯ СВОДКА (вместо кучи одинаковых строк)
    if loaded_symbols:
        print(f"✅ Загружено: {len(loaded_symbols)} символов ({', '.join(loaded_symbols)})")
    else:
        print("❌ Нет загруженных символов — бэктест не запустится")

    if failed_symbols:
        print(f"⚠️ Пропущено: {len(failed_symbols)} символов из-за отсутствия данных или ошибок:")
        for sym in failed_symbols:
            print(f"   тАв {sym}")

    # тХРтХРтХР ╨Ц╨г╨а╨Э╨Р╨Ы тХРтХРтХР
    journal_df = load_journal(JOURNAL_FILE, COLUMNS)

    # тХРтХРтХР ╨Р╨Ъ╨в╨Ш╨Т╨Э╨л╨Х ╨б╨в╨а╨Р╨в╨Х╨У╨Ш╨Ш тХРтХРтХР
    active_strategies = {}

    # тХРтХРтХР ╨У╨Х╨Э╨Х╨а╨Р╨ж╨Ш╨п ╨Я╨а╨Ю╨Я╨г╨й╨Х╨Э╨Э╨л╨е ╨Ю╨в╨з╨Б╨в╨Ю╨Т тХРтХРтХР
    print("\nПроверка пропущенных daily отчётов...")
    registry_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'journals', 'strategy_registry.csv')
    if os.path.exists(registry_path):
        with open(registry_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if rows:
                first_date_str = rows[0].get('activated_at', '')
                if first_date_str:
                    first_date = None
                    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
                        try:
                            first_date = datetime.strptime(first_date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    if first_date is None:
                        print("  ⚠️  Реестр: неверный формат activated_at — отчёты за прошлые дни пропущены", flush=True)
                        first_date = date.today()
                    yesterday = date.today() - timedelta(days=1)
                    if first_date <= yesterday:
                        generate_missing_reports(first_date, yesterday)
    else:
        print("  ⚠️  Реестр не найден — отчёты будут генерироваться с первого дня")

    # тХРтХРтХР ╨Я╨Х╨а╨Т╨л╨Щ ╨а╨Р╨б╨з╨Б╨в тХРтХРтХР
    print("\nБэктест (первый расчёт)...")

    FORCE_RECALC = bt_cfg.force_recalc
    night_reset_path = os.path.join(_checkpoint_dir(), 'night_reset.json')
    full_recalc_marker_path = os.path.join(_checkpoint_dir(), 'last_full_recalc.json')
    # Диагностика: куда именно пишутся чекпойнты. Молчаливый «пропуск» каталога в
    # синке три дня скрывал, что папки нет вовсе — путь должен быть виден в логе.
    print(f"  📁 Чекпойнты: {_checkpoint_dir()}", flush=True)
    is_first_run = not os.path.exists(night_reset_path)
    manual_full = bool(bt_cfg.full_recalc_mode)   # ручной полный пересчёт при запуске
    
    # тХРтХРтХР ╨Р╨Т╨в╨Ю╨Ь╨Р╨в╨Ш╨з╨Х╨б╨Ъ╨Ш╨Щ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨Я╨Х╨а╨Х╨б╨з╨Б╨в ╨Э╨Р ╨Т╨л╨е╨Ю╨Ф╨Э╨л╨е (╨б╨▒/╨Т╤Б) тХРтХРтХР
    now = datetime.now()
    weekend_full_due = False
    days_since_full = None   # для диагностики: сколько дней с последнего ПОЛНОГО пересчёта
    _bg_started = False      # True = ПОЛНЫЙ проход поставлен фоновым job (async-ветка ниже)
    if bt_cfg.auto_weekend_recalc or bt_cfg.full_recalc_daily:  # окно выходных + догон в будни, если уик-энд пропущен
        # Один ПОЛНЫЙ пересчёт на окно выходных (Сб–Вс). Если окно пропущено — догон в будни (см. _full_recalc_due).
        # Дата последнего ПОЛНОГО пересчёта берётся из last_full_recalc.json
        # (night_reset.json не годится — его перезаписывают в том числе будние реранки).
        if not is_first_run:
            try:
                with open(full_recalc_marker_path, 'r', encoding='utf-8') as _f:
                    _reset_ts = json.load(_f).get('last_full_recalc', '')
                if _reset_ts:
                    _last_full_date = datetime.fromisoformat(_reset_ts).date()
                    days_since_full = (now.date() - _last_full_date).days
                    # Правило: один ПОЛНЫЙ на окно выходных (Сб–Вс) + догон в будни, если окно пропущено.
                    # Пора ли ПОЛНЫЙ: окно выходных (Сб–Вс) либо догон, если окно пропущено
                    weekend_full_due, days_since_full, _last_full_date = _full_recalc_due(
                        now, full_recalc_marker_path, bt_cfg.full_recalc_min_gap_days,
                        daily=bt_cfg.full_recalc_daily)
                    if False and not weekend_full_due:  # краткое решение печатает _log_recalc_chain()
                        print(f"  ℹ️  ПОЛНЫЙ пересчёт уже был ({days_since_full} дн. назад / в текущем окне выходных) — повторно НЕ запускаем. "
                              + (" Ждём открытия рынка (Пн) — торговли в выходные нет." if now.weekday() >= 5 else " Работаем в обычном режиме (мониторинг сигналов)."))
                else:
                    # Не можем подтвердить, что сегодня уже считали — считаем заново
                    weekend_full_due = True
            except (OSError, ValueError, json.JSONDecodeError):
                weekend_full_due = True
        # Полный пересчёт держит боевой цикл закрытым 150–230 мин: пока он идёт,
        # бары/сигналы/трейлинг не проверяются. full_recalc_only_flat=True — отложить.
        # Днём полный пересчёт откладываем до ночного окна (кроме первого запуска).
        if (weekend_full_due and not is_first_run
                and not _in_full_window(now, bt_cfg.full_refresh_window_end_hour,
                                        bt_cfg.night_backtest_hour)):
            print(f"  ⏸  ПОЛНЫЙ пересчёт отложен до ночного окна "
                  f"({bt_cfg.night_backtest_hour}:00тАУ{bt_cfg.full_refresh_window_end_hour}:00): "
                  f"сейчас {now.strftime('%H:%M')} — работаем на чекпойнтах")
            weekend_full_due = False
        if weekend_full_due and _has_open_positions():
            if bt_cfg.full_recalc_only_flat:
                print("  ⏸  ПОЛНЫЙ пересчёт отложен: есть открытые позиции "
                      "(full_recalc_only_flat=True)")
                weekend_full_due = False
            else:
                print("  ⚠️  ПОЛНЫЙ пересчёт при открытых позициях: пока идёт расчёт, "
                      "бары и сигналы не проверяются", flush=True)
        if is_first_run or weekend_full_due:
            FORCE_RECALC = True
            weekend_full_due = True
            # Фоновый режим: полный проход ставим в фон, а стартуем на чекпойнтах — иначе
            # рестарт внутри ночного окна снова встал бы на 150–230 мин. Синхронно оставляем
            # первый запуск (чекпойнтов ещё нет) и ручной full_recalc_mode.
            if (getattr(bt_cfg, 'async_backtest', False)
                    and not is_first_run and not manual_full):
                _bg_start(bt_cfg.symbols, symbol_data, strategy_params, bt_cfg)
                FORCE_RECALC = False
                weekend_full_due = False
                _bg_started = True      # честная строка решения ниже: полный проход уже в фоне
                print(f"  🚀 ПОЛНЫЙ пересчёт поставлен в фон "
                      f"({backtest_worker_count(bt_cfg)} процессов) — старт на чекпойнтах, "
                      f"результат применится по завершении")
            else:
                print(f"  🌙 ПОЛНЫЙ пересчёт ({now.strftime('%A')} {now.strftime('%Y-%m-%d %H:%M')}) — окно выходных / догон")

        # тФАтФА ╨а╤Г╤З╨╜╨╛╨╣ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В (full_recalc_mode=True) тАФ ╤В╨╛╨╢╨╡ ╨▓ ╤Д╨╛╨╜ тФАтФА
        # Раньше ручной режим всегда шёл синхронно и держал боевой цикл закрытым
        # 150–230 мин. Теперь при async_backtest он ставится фоновым job (как ночной):
        # цикл продолжает торговать, результат применяется по завершении.
        if manual_full and not _bg_started:
            if getattr(bt_cfg, 'async_backtest', False) and not is_first_run:
                _bg_start(bt_cfg.symbols, symbol_data, strategy_params, bt_cfg)
                _bg_started = True
                manual_full = False      # стартовый прогон ниже — реранк по чекпойнтам
                FORCE_RECALC = False
                print(f"  🚀 РУЧНОЙ ПОЛНЫЙ пересчёт поставлен в фон "
                      f"({backtest_worker_count(bt_cfg)} процессов) — цикл не блокируется")
            else:
                print("  🌙 РУЧНОЙ ПОЛНЫЙ пересчёт — синхронно (async_backtest выключен "
                      "или это первый запуск без чекпойнтов)")
        
            
            

    # Маркера нет (напр. сразу после обновления) — фиксируем лучшую известную дату,
    # чтобы не запускать ПОЛНЫЙ пересчёт «вслепую» на каждом старте.
    if not os.path.exists(full_recalc_marker_path):
        _seed = _read_last_full_recalc(full_recalc_marker_path)
        if _seed is not None:
            _write_full_recalc_marker(full_recalc_marker_path,
                                      ts=datetime.combine(_seed, datetime.min.time()))

    _log_recalc_chain(now, night_reset_path, full_recalc_marker_path, is_first_run,
                      bt_cfg.full_recalc_min_gap_days, days_since_full, weekend_full_due or _bg_started, manual_full)

    if manual_full:
        print("  ⚙️  full_recalc_mode=True — РУЧНОЙ ПОЛНЫЙ ПЕРЕСЧЁТ всех стратегий")
    elif is_first_run:
        print("  🆕 Нет кэша прошлого прогона — считаем ВСЕ стратегии с нуля")
    else:
        print("  ✅ Есть кэш прошлого прогона — используем чекпоинты (работа по чекпойнтам)")

    try:
        # Маркер ПОЛНОГО пересчёта здесь НЕ пишем: его двигает сам run_full_backtest,
        # и только если прогон покрыл план на 100%. Раньше маркер ставился ЗАРАНЕЕ —
        # и упавший/неполный прогон молча «съедал» следующую ночь.
        #
        # Предварительной записи маркера здесь больше нет (см. выше).
        # Дубль записи маркера убран 27.10
        all_top, all_results = run_full_backtest(
            bt_cfg.symbols, symbol_data, strategy_params, bt_cfg,
            test_strategy=None,
            test_mode=False,
            force_recalc=FORCE_RECALC or manual_full or weekend_full_due,
            incremental=False,   # ИНКРЕМЕНТ УДАЛЁН: только полные пересчёты
            is_night_run=is_first_run or manual_full or weekend_full_due
        )

        # После первого прогона записываем night_reset.json
        if is_first_run or manual_full or weekend_full_due:
            _write_night_reset(night_reset_path, start_time, len(bt_cfg.symbols), len(all_results))
            # Маркер последнего ПОЛНОГО пересчёта (реранки этот файл не трогают)
            # Маркер двигает сам прогон: здесь только проверяем, что он его заслужил.
            import functions as _fn_mk
            if getattr(_fn_mk, 'LAST_RUN_KIND', None) == 'full':
                _write_full_recalc_marker(full_recalc_marker_path)
            else:
                print("  ⚠️  Маркер ПОЛНОГО пересчёта не сдвигаю: прогон не покрыл "
                      "план — следующей ночью пересчёт повторится", flush=True)

    except Exception as exc:
        print(f"\n[КРИТИЧНО] Первый бэктест не завершился: {exc!r}", flush=True)
        print("Сохранены чекпойнты готовых символов — повторный запуск продолжит с них.", flush=True)
        try:
            save_journal(journal_df, JOURNAL_FILE)
        except Exception:
            pass



        try:
            mt5.shutdown()
        except Exception:
            pass



        raise SystemExit(1) from exc

    acc = mt5.account_info()
    balance = acc.balance if acc else 1_000_000
    if acc is not None:
        mode_name = {0: 'demo', 1: 'contest', 2: 'real'}.get(acc.trade_mode, str(acc.trade_mode))
        print(f"Счёт: {acc.login} | Сервер: {acc.server} | Валюта: {acc.currency} | Режим: {mode_name}")
    print(f"Баланс: {balance:.0f} руб | Квота риска: {balance * risk_cfg.max_risk_pct:.0f} руб | Порог score >= {risk_cfg.min_score}")

    deduped_results = all_results
    print(f"После дедупликации: {len(deduped_results)} комбинаций")

    active = distribute_lots(deduped_results, symbol_data, balance,
                             risk_cfg.max_risk_pct, risk_cfg.min_lot, risk_cfg.min_score, risk_cfg.max_per_type, risk_cfg.per_trade_risk_pct)
    if getattr(steering_cfg, 'tree_weighting', False):
        try:
            apply_tree_weighting(
                active, symbol_data, balance, risk_cfg.max_risk_pct, risk_cfg.min_lot,
                lookback_days=steering_cfg.lookback_days,
                min_trades=steering_cfg.min_trades)
        except Exception as _tw_e:
            print(f"  [WARN] tree-weighting: {_tw_e!r}", flush=True)

    # тФАтФА ╨Я╤А╨╡╨╝╨╕╤П/╨┤╨╕╤Б╨║╨╛╨╜╤В ╨║ ╨╛╨▒╤К╤С╨╝╤Г ╨┐╨╛ ╨╗╤Г╤З╤И╨╡╨╣/╤Е╤Г╨┤╤И╨╡╨╣ ╤В╨░╨║╤В╨╕╨║╨╡ ╨▓╤Е╨╛╨┤╨░ (┬▒20%) тФАтФА
    # Штурвал ниже переложит лоты ещё раз и применит тильт повторно (идемпотентно),
    # но если штурвал не отработает (нет квот/бюджета), план всё равно должен
    # нести надбавку — иначе дэшборд покажет «сырой» объём.
    if getattr(steering_cfg, 'tactic_tilt_enabled', True):
        try:
            import tactic_tilt as _tt
            _tt.apply_tactic_tilt(
                active, when=datetime.now(),
                pct=getattr(steering_cfg, 'tactic_tilt_pct', 0.20),
                window_days=getattr(steering_cfg, 'tactic_tilt_window_days', 90),
                min_trades=getattr(steering_cfg, 'tactic_tilt_min_trades', 2),
                weekday_only=getattr(steering_cfg, 'tactic_tilt_weekday_only', False),
                min_lot=risk_cfg.min_lot, log=print)
        except Exception as _tt_e:
            print(f"  [WARN] TILT: {_tt_e!r}", flush=True)

    print(f"Активировано {len(active)} стратегий из {len(deduped_results)} комбинаций")

    for i, r in enumerate(active):
        stype = r.get('type', 'stoch')
        pmax = r.get('parabolic_max')
        pmax_str = f" Max={pmax:.2f}" if pmax is not None else ""
        print(f"  {i + 1}. {r['symbol']} {stype} K={r['param_key']}{pmax_str} "
              f"SL={r['sl_points']} TP={r['tp_points']} "
              f"profit={r['profit']:+.1f} PF={r['profit_factor']:.2f} "
              f"WR={r['win_rate']:.0f}% trades={r['n_trades']} "
              f"score={r['score']:.3f} lot={r['lot']}")

    write_ranking(active, all_results, JOURNAL_DIR, bt_cfg.backtest_days, len(active), None)

    sync_active_strategies(active, datetime.now(), symbol_data, active_strategies,
                           close_order, get_deal_exit_price, record_trade,
                           strategy_key, assign_magic, bt_cfg.magic_base, len(active))

    # тФАтФА ╨б╤В╨░╤В╤Г╤Б ╤Б╨╡╨╝╨╡╨╣╤Б╤В╨▓ ╨▓ ╨С╨Ф (╨┐╨╛╤Б╨╗╨╡ ╤А╨╡╤А╨░╨╜╨║╨░): ╤Г╤З╨░╤Б╤В╨╕╨╡ ╨▓ ╤А╤Н╨╜╨║╨╕╨╜╨│╨╡ ╨╕ ╨│╨╛╤В╨╛╨▓╨╜╨╛╤Б╤В╤М тФАтФА
    _record_family_status(all_results, active)

    write_active_state(active, active_strategies, balance, risk_cfg.max_risk_pct, JOURNAL_DIR)

    # тФАтФА ╨и╤В╤Г╤А╨▓╨░╨╗ ╨┐╤А╨╕ ╤Б╤В╨░╤А╤В╨╡: ╨╛╨▒╤П╨╖╨░╤В╨╡╨╗╤М╨╜╤Л╨╣ ╤И╨░╨│, ╨╜╨╡ ╨╢╨┤╤С╨╝ ╨╜╨╛╤З╨╜╨╛╨│╨╛ ╨▒╤Н╨║╤В╨╡╤Б╤В╨░ тФАтФА
    if steering_cfg.enabled:
        _wheel_st = run_steering_wheel(
            active_strategies, active, symbol_data, balance,
            risk_cfg, steering_cfg, journal_dir=JOURNAL_DIR, tag='(старт)')
        if _wheel_st.get('changed') or _wheel_st.get('synced'):
            write_active_state(active, active_strategies, balance,
                               risk_cfg.max_risk_pct, JOURNAL_DIR)
    else:
        print("  [WHEEL] ОТКЛЮЧЁН: steering_cfg.enabled=False — квоты/лоты не пересчитываются.",
              flush=True)

    # тФАтФА ╨Ю╨┤╨╜╨╛╨║╤А╨░╤В╨╜╤Л╨╣ ╨Ф╨Ю╨У╨Ю╨Э ╨╕╤Б╤В╨╛╤А╨╕╨╕ ╤Б╨┤╨╡╨╗╨╛╨║ ╨┐╤А╨╕ ╤Б╤В╨░╤А╤В╨╡ (╨▓ ╤Д╨╛╨╜╨╡) тФАтФА
    # Широкое окно (30 суток) закрывает дыры, накопленные простоем бота/машины или
    # прежним «сжимающимся» окном ingest (сделка 20.10 16:45 не попала именно так).
    # Идемпотентно (UPSERT по deal_ticket), идёт в фоне — цикл не задерживается.
    _ingest_start(days=30, verbose=True)

    print(f"\nЗапуск цикла. Ctrl+F2 для остановки.\n")
    if now.weekday() >= 5 and not weekend_full_due:
        print("⏳ Выходной: полный пересчёт уже был выполнен ранее — повторно НЕ считаем.\n"
              "   Режим ожидания открытия рынка (Пн). Торговли в выходные нет.\n")
    print("✅ " + ('Минимальный режим работы — ждём открытия рынка (Пн).' if now.weekday() >= 5 else 'Запущен рабочий цикл (мониторинг сигналов и исполнение).') + "\n"
          "   В будни: мониторинг сигналов. Окно выходных: один полный пересчёт (с догоном в будни, если уик-энд пропущен).\n")

    # тХРтХРтХР ╨У╨Ы╨Р╨Т╨Э╨л╨Щ ╨ж╨Ш╨Ъ╨Ы тХРтХРтХР
    last_full_backtest_date = None  # не «сегодня»: ночной ре-ранк (чекпойнты+штурвал) должен отработать и в день рестарта
    last_mode_check = datetime.now().date()
    last_state_write = datetime.now()
    # Штурвал: время последнего пересчёта квот/перекладки лотов (не зависит от бэктеста).
    # На старте штурвал уже отработал выше → отсчёт interval_sec идёт от текущего момента.
    last_steering = datetime.now() if steering_cfg.enabled else datetime.min
    last_journal_write = datetime.now()
    journal_month = datetime.now().strftime('%Y%m')
    last_ticks_time = datetime.now()
    last_conn_warn_time = datetime.min
    last_balance_refresh = datetime.now()
    last_quota_recalc = datetime.now()
    last_equity_sample = datetime.min          # сэмплер floating → trades_db (daily_peak/equity_samples)
    last_trades_ingest = datetime.min          # добор сделок в trades_db (deals) в течение дня
    EQUITY_SAMPLE_INTERVAL_SEC = 300           # свой интервал сэмплинга, независим от poll_interval
    # Добор сделок в trades_db (deals): закрытия пишутся сразу (strategy_engine._record_close →
    # trades_db.record_position), но страховочный ingest нужен и днём, а не только в 3:00.
    TRADES_DB_INGEST_INTERVAL_SEC = 900        # 15 мин
    def _net_cashflow(since_dt):
        """Чистый внешний кэшфлоу (пополнения − выводы) в рублях с момента since_dt.
        Нужен, чтобы гварды риска не принимали депо/вывод за торговый убыток."""
        try:
            _deals = mt5.history_deals_get(since_dt, datetime.now() + timedelta(hours=6))
        except Exception:
            return 0.0
        if not _deals:
            return 0.0
        return float(sum(d.profit for d in _deals
                         if d.type in (mt5.DEAL_TYPE_BALANCE, mt5.DEAL_TYPE_CREDIT)))

    initial_equity = None
    daily_start_balance = None
    daily_start_date = None
    daily_start_dt = None
    initial_equity_dt = None
    daily_stop_notified = False  # [STOP] печатаем и закрываем позиции один раз за день
    first_run = True  # Флаг первого запуска — нужен для полного пересчёта

    try:
        while True:
            now = datetime.now()

            # тФАтФА ╨б╤Н╨╝╨┐╨╗╨╡╤А ╨╜╨╡╤А╨╡╨░╨╗╨╕╨╖╨╛╨▓╨░╨╜╨╜╨╛╨╣ ╨┐╤А╨╕╨▒╤Л╨╗╨╕ (trades_db): ╤Б╨▓╨╛╨╣ ╨╕╨╜╤В╨╡╤А╨▓╨░╨╗ ~300 ╤Б тФАтФА
            # Торговую логику не трогаем: только пишем floating по категориям в daily_peak
            # и снимок счёта в equity_samples. Fail-safe — ошибка БД не роняет пайплайн.
            if (now - last_equity_sample).total_seconds() >= EQUITY_SAMPLE_INTERVAL_SEC:
                last_equity_sample = now
                try:
                    import trades_db
                    trades_db.sample_positions(interval=EQUITY_SAMPLE_INTERVAL_SEC)
                    # тФАтФА ╨Я╨╕╨║-╤В╤А╨╕╨╝: ╤Д╨╕╨║╤Б╨░╤Ж╨╕╤П ╨┐╨╛ ╨Ш╨б╨в╨Ю╨а╨Ш╨з╨Х╨б╨Ъ╨Ю╨Ь╨г ╨┐╨╕╨║╤Г тВ╜/╨╗╨╛╤В тФАтФАтФАтФАтФАтФАтФАтФАтФАтФА
                    # Идёт сразу после сэмплера (пики уже свежие). По умолчанию
                    # ТЕНЕВОЙ режим: только лог `[TRIM] would …` + запись решения
                    # в peak_trim; реальные закрытия включаются в config.PeakTrimParams
                    # (enabled=True). Fail-safe: ошибка не роняет ни сэмплер, ни цикл.
                    try:
                        import peak_trim
                        peak_trim.scan_and_trim()
                    except Exception as _trim_err:
                        print(f"  [WARN] peak_trim: {_trim_err!r}", flush=True)
                except Exception as _smp_err:
                    print(f"  [WARN] trades_db.sample: {_smp_err!r}", flush=True)

            # тФАтФА ╨Ф╨╛╨▒╨╛╤А ╤Б╨┤╨╡╨╗╨╛╨║ ╨▓ trades_db (deals) тАФ ╨▓ ╨д╨Ю╨Э╨Х, ╤Ж╨╕╨║╨╗ ╨╜╨╡ ╨▒╨╗╨╛╨║╨╕╤А╤Г╨╡╤В╤Б╤П тФАтФА
            # Закрытия и так пишутся сразу (_record_close → trades_db.record_position),
            # но это страховка от пропусков (рестарт, закрытие «не нашей» рукой).
            if (now - last_trades_ingest).total_seconds() >= TRADES_DB_INGEST_INTERVAL_SEC:
                last_trades_ingest = now
                try:
                    import trades_db
                    _ingest_start(days=1)     # фон: MT5-запрос и запись в БД не тормозят цикл
                    if _ingest_error:         # ошибка предыдущего фонового добора
                        print(f"  [WARN] trades_db.ingest: {_ingest_error}", flush=True)
                        _ingest_error = None
                except Exception as _ing_err:
                    print(f"  [WARN] trades_db.ingest: {_ing_err!r}", flush=True)

            # Смена дня
            if now.date() != last_mode_check:
                last_mode_check = now.date()
                print(f"\n[{now}] Новый день")
                if now.weekday() >= 5:  # Сб=5, Вс=6
                    print("  ℹ Расчёты завершены. Ожидание открытия рынка (Пн) — минимальный режим.")

            # Ночной пересчёт: раз в сутки с 3:00 (будни — инкремент, выходные — ПОЛНЫЙ)
            # Будни — реранк по чекпойнтам (+инкремент); выходные — полный пересчёт
            # Выходной полный пересчёт управляется auto_weekend_recalc (True по умолчанию)
            is_weekday = now.weekday() < 5  # Пн=0 ... Пт=4
            is_weekend = now.weekday() >= 5  # Сб=5, Вс=6
            
            # Ночной прогон: раз в день после 3:00, повторно в тот же день не запускается
            # force_recalc=True (полный) ставится только на выходных; в будни — реранк
            
            # тФАтФА ╨д╨╛╨╜╨╛╨▓╤Л╨╣ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В: ╨┐╤А╨╕╤С╨╝ ╤А╨╡╨╖╤Г╨╗╤М╤В╨░╤В╨░ тФАтФА
            # Job считался в отдельном потоке: цикл всё это время жил обычной жизнью
            # (тики, бары, сигналы, трейлинг, аварийные защиты). Применяем его результат
            # тем же путём, что и синхронный ночной прогон (см. блок ниже).
            _bg_finished = _bg_poll()
            if _bg_finished and _bg_failed is not None:
                print(f"\n  ⚠️  Фоновый ПОЛНЫЙ пересчёт не удался: {_bg_failed} — "
                      f"чекпойнты могут быть обновлены частично, повторим следующей ночью",
                      flush=True)
                last_full_backtest_date = now.date()
                # Падение фонового job — тоже событие пересчёта: пишем строку
                # kind='incomplete', чтобы во вкладке Backtest была ОРАНЖЕВАЯ точка,
                # а не пустота (молчаливый провал — то, из-за чего это тянулось неделями).
                try:
                    from functions import append_backtest_history as _abh
                    _abh(_bg_elapsed_min * 60.0, 0, 0, 0, kind='incomplete',
                         is_night_run=True, combos_done=0, combos_plan=0,
                         symbols_total=len(bt_cfg.symbols), coverage_pct=0.0,
                         ok=False, error=str(_bg_failed)[:300])
                except Exception as _je:
                    print(f"  [WARN] журнал прогонов: {_je!r}", flush=True)
            elif _bg_ready:
                print(f"\n[{now.strftime('%H:%M:%S')}] ✅ Фоновый ПОЛНЫЙ пересчёт завершён "
                      f"({_bg_elapsed_min:.0f} мин) — применяю результат, цикл не останавливался",
                      flush=True)

            should_run_backtest = False
            if _bg_ready:
                # Результат фонового job готов → идём ночным путём: считать нечего,
                # свежие чекпойнты уже на диске (см. _bg_apply внутри блока ниже).
                should_run_backtest = True
            elif now.hour >= bt_cfg.night_backtest_hour and now.date() != last_full_backtest_date:
                should_run_backtest = True
            
            if should_run_backtest:
                # Фоновый job завершился → результат применяем СЕЙЧАС: чекпойнты уже
                # свежие, пересчитывать нечего (см. force_recalc ниже). Флаг переносим в
                # локальную переменную, чтобы _bg_ready не «залипал» на следующие ночи:
                # _bg_apply живёт только текущую итерацию и решает: считать ли этот прогон
                # ПОЛНЫМ (маркер пересчёта) и надо ли ставить новый job.
                _bg_apply = _bg_ready
                _bg_ready = False
                
                # auto_weekend_recalc=False — в выходной пересчёт не запускаем
                if is_weekend and not bt_cfg.auto_weekend_recalc and not _bg_apply:
                    print(f"\n[{now.strftime('%H:%M:%S')}] ⏸ Выходной ({now.strftime('%A')}) — авто-пересчёт отключён (auto_weekend_recalc=False)")
                    last_full_backtest_date = now.date()
                    continue
                
                # Пора ли ПОЛНЫЙ: окно выходных (Сб–Вс) либо догон в будни
                _night_full_due, _, _ = _full_recalc_due(
                    now, full_recalc_marker_path, bt_cfg.full_recalc_min_gap_days,
                    daily=bt_cfg.full_recalc_daily)
                if not bt_cfg.auto_weekend_recalc and not bt_cfg.full_recalc_daily:
                    _night_full_due = False

                # тФАтФА ╨д╨╛╨╜╨╛╨▓╤Л╨╣ job ╤Г╨╢╨╡ ╨╛╤В╤А╨░╨▒╨╛╤В╨░╨╗ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╤А╨╛╤Е╨╛╨┤ тФАтФА
                # Фиксируем это как ПОЛНЫЙ пересчёт, даже если по календарю окно выходных
                # закрыто: иначе не сдвинется маркер last_full_recalc, и следующей ночью
                # стартует ещё один полный проход.
                if _bg_apply:
                    _night_full_due = True

                # тФАтФА ╨Ю╨║╨╜╨╛ ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ тФАтФА
                # Синхронный режим (async_backtest=False): полный пересчёт держит боевой цикл
                # закрытым 150–230 мин — бары не опрашиваются, сигналы не рождаются,
                # трейлинг и аварийные защиты (daily loss, equity stop, margin) не работают.
                # Поэтому днём полный проход откладывается до ночного окна (см. ниже).
                # В фоновом режиме (async_backtest=True) цикл не блокируется, поэтому
                # ограничение по времени суток становится мягким: днём берём чекпойнты,
                # а полный проход уходит в ночное окно.
                if not _bg_apply and not _in_full_window(now, bt_cfg.full_refresh_window_end_hour, bt_cfg.night_backtest_hour):
                # (в фоновом режиме окно не критично — цикл всё равно не встанет)
                # Окно ПОЛНОГО пересчёта: 3:00–10:00 в будни; в выходные — без ограничения.
                    if _night_full_due:
                        print(f"  ⏸  ПОЛНЫЙ пересчёт отложен до ночного окна "
                              f"({bt_cfg.night_backtest_hour}:00тАУ{bt_cfg.full_refresh_window_end_hour}:00): "
                              f"сейчас {now.strftime('%H:%M')} — работаем по чекпойнтам")
                    _night_full_due = False
                if _night_full_due and not _bg_apply and _has_open_positions():
                    if bt_cfg.full_recalc_only_flat:
                        print("  ⏸  ПОЛНЫЙ пересчёт отложен: есть открытые позиции "
                              "(full_recalc_only_flat=True) — в этот цикл работаем по чекпойнтам")
                        _night_full_due = False
                    else:
                        print("  ⚠️  ПОЛНЫЙ пересчёт при открытых позициях: пока идёт расчёт, "
                              "бары и сигналы не проверяются", flush=True)

                # Определяем причину запуска
                if _night_full_due:
                    _reason = " — результат фонового job" if _bg_apply else " — окно выходных / догон..."
                    print(f"\n[{now.strftime('%H:%M:%S')}] ⏺ Ночной ПОЛНЫЙ пересчёт ({now.strftime('%A')}){_reason}")
                elif is_weekday:
                    print(f"\n[{now.strftime('%H:%M:%S')}] 🔄 Ночной РЕРАНК: чекпойнты + штурвал (сетку не пересчитываем)")
                else:
                    print(f"\n[{now.strftime('%H:%M:%S')}] ⏺ Выходной ({now.strftime('%A')}) — реранк по чекпойнтам (сетку не пересчитываем)")

                try:
                    # тФАтФА ╨д╨╛╨╜╨╛╨▓╤Л╨╣ (async) ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В: ╤Ж╨╕╨║╨╗ ╨▒╨╛╨╗╤М╤И╨╡ ╨╜╨╡ ╨▒╨╗╨╛╨║╨╕╤А╤Г╨╡╤В╤Б╤П тФАтФА
                    # Было: run_full_backtest — синхронный вызов, 150–230 минут боевой цикл
                    # стоял. Стало: тяжёлая часть считается в отдельном потоке
                    # (backtest_job.BacktestJob), а результат применяется по завершении job —
                    # следующей итерацией, повторным входом в этот блок по _bg_ready.
                    if (getattr(bt_cfg, 'async_backtest', False)
                            and _night_full_due and not _bg_apply):
                        if _bg_running():
                            print(f"  ⏳ Фоновый пересчёт уже идёт — новый не ставлю", flush=True)
                        else:
                            _bg_start(bt_cfg.symbols, symbol_data, strategy_params, bt_cfg)
                            print(f"  🚀 Фоновый ПОЛНЫЙ пересчёт поставлен "
                                  f"({backtest_worker_count(bt_cfg)} процессов, приоритет below normal) — "
                                  f"боевой цикл продолжает работать", flush=True)
                        last_full_backtest_date = now.date()
                        continue

                    _, all_results = run_full_backtest(
                        bt_cfg.symbols, symbol_data, strategy_params, bt_cfg,
                        test_strategy=None,
                        test_mode=False,
                        # Фоновый job уже прогрел чекпойнты → пересчитывать нечего: читаем
                        # готовое (реранк по чекпойнтам, ~1 с). Иначе — обычный синхронный путь.
                        force_recalc=(bool(_night_full_due) and not _bg_apply),
                        is_night_run=True
                    )
                except Exception as exc:
                    print(f"\n[WARN] Ночной перерасчёт не удался: {exc!r} — "
                          f"оставляем текущие стратегии, повторим завтра в 3:00.", flush=True)
                    # Провал виден во вкладке Backtest (оранжевая точка), а не только в логе.
                    if _night_full_due:
                        try:
                            from functions import append_backtest_history as _abh
                            _abh(0.0, 0, 0, 0, kind='incomplete', is_night_run=True,
                                 combos_done=0, combos_plan=0,
                                 symbols_total=len(bt_cfg.symbols), coverage_pct=0.0,
                                 ok=False, error=str(exc)[:300])
                        except Exception as _je:
                            print(f"  [WARN] журнал прогонов: {_je!r}", flush=True)
                    continue
                last_full_backtest_date = now.date()
                acc = mt5.account_info()
                balance = acc.balance if acc else 1_000_000
                deduped_results = all_results
                active = distribute_lots(deduped_results, symbol_data, balance,
                                         risk_cfg.max_risk_pct, risk_cfg.min_lot, risk_cfg.min_score, risk_cfg.max_per_type, risk_cfg.per_trade_risk_pct)
                if getattr(steering_cfg, 'tree_weighting', False):
                    try:
                        apply_tree_weighting(
                            active, symbol_data, balance, risk_cfg.max_risk_pct, risk_cfg.min_lot,
                            lookback_days=steering_cfg.lookback_days,
                            min_trades=steering_cfg.min_trades)
                    except Exception as _tw_e:
                        print(f"  [WARN] tree-weighting: {_tw_e!r}", flush=True)

                # тФАтФА ╨Я╤А╨╡╨╝╨╕╤П/╨┤╨╕╤Б╨║╨╛╨╜╤В ╨║ ╨╛╨▒╤К╤С╨╝╤Г ╨┐╨╛ ╤В╨░╨║╤В╨╕╨║╨╡ ╨▓╤Е╨╛╨┤╨░ (┬▒20%): ╨║╨╛╨╜╨╡╤Ж ╤А╨╡╤А╨░╨╜╨║╨░ тФАтФА
                # Та же логика, что в run_steering_wheel ниже (там — для лотов штурвала);
                # здесь — чтобы план нёс надбавку, даже если штурвал не тронет лоты.
                if getattr(steering_cfg, 'tactic_tilt_enabled', True):
                    try:
                        import tactic_tilt as _tt
                        _tt.apply_tactic_tilt(
                            active, when=now,
                            pct=getattr(steering_cfg, 'tactic_tilt_pct', 0.20),
                            window_days=getattr(steering_cfg, 'tactic_tilt_window_days', 90),
                            min_trades=getattr(steering_cfg, 'tactic_tilt_min_trades', 2),
                            weekday_only=getattr(steering_cfg, 'tactic_tilt_weekday_only', False),
                            min_lot=risk_cfg.min_lot, log=print)
                    except Exception as _tt_e:
                        print(f"  [WARN] TILT: {_tt_e!r}", flush=True)
                print(f"Баланс: {balance:.0f} руб | Квота: {balance * risk_cfg.max_risk_pct:.0f} руб | "
                      f"Активировано {len(active)} из {len(deduped_results)} (всего {len(all_results)})")

                # тФАтФА ╨б╤В╤А╨░╤Е╨╛╨▓╨║╨░: ╨┐╤Г╤Б╤В╨╛╨╣ ╨┐╤А╨╛╨│╨╛╨╜ ╨╜╨╡ ╨┤╨╛╨╗╨╢╨╡╨╜ ╤Б╤В╨╕╤А╨░╤В╤М ╨┐╨╗╨░╨╜ тФАтФА
                # Если пересчёт не дал ни одной стратегии (несовместимые/пустые чекпойнты,
                # нет данных символов), пустой active_state.json писать нельзя: Daily Plan
                # оставался без строк, а ranking.txt обнулялся в «0 комбинаций».
                # Пропускаем итерацию — прежний план живёт до следующего прогона.
                if not active and os.path.exists(os.path.join(JOURNAL_DIR, 'active_state.json')):
                    print("  [ERROR] Ночной пересчёт дал 0 стратегий — план и ranking НЕ "
                          "перезаписаны (проверь чекпойнты и данные символов)", flush=True)
                    last_full_backtest_date = now.date()
                    continue
                write_ranking(active, all_results, JOURNAL_DIR, bt_cfg.backtest_days, len(active), None)
                sync_active_strategies(active, now, symbol_data, active_strategies,
                                       close_order, get_deal_exit_price, record_trade,
                                       strategy_key, assign_magic, bt_cfg.magic_base, len(active))

                # тФАтФА ╨б╤В╨░╤В╤Г╤Б ╤Б╨╡╨╝╨╡╨╣╤Б╤В╨▓ ╨▓ ╨С╨Ф (╨┐╨╛╤Б╨╗╨╡ ╤А╨╡╤А╨░╨╜╨║╨░): ╤Г╤З╨░╤Б╤В╨╕╨╡ ╨▓ ╤А╤Н╨╜╨║╨╕╨╜╨│╨╡ ╨╕ ╨│╨╛╤В╨╛╨▓╨╜╨╛╤Б╤В╤М тФАтФА
                _record_family_status(all_results, active)

                # тФАтФА ╨и╤В╤Г╤А╨▓╨░╨╗: ╨┐╨╗╨░╨▓╨╜╨╛╨╡ ╨┐╨╡╤А╨╡╤А╨░╤Б╨┐╤А╨╡╨┤╨╡╨╗╨╡╨╜╨╕╨╡ ╨║╨▓╨╛╤В ╨┐╨╛ ╤А╨╡╨░╨╗╤М╨╜╤Л╨╝ ╤Б╨┤╨╡╨╗╨║╨░╨╝ тФАтФА
                if False:  # DEPRECATED: логика вынесена в run_steering_wheel() (вызывается безусловно ниже)
                    try:
                        # тФАтФА ╨Ш╤Б╤В╨╛╤З╨╜╨╕╨║: Strategy Tree (╨╛╨║╨╜╨╛ ╨░╨╗╨╗╨╛╨║╨░╤Ж╨╕╨╕ lookback_days) тФАтФА
                        # Та же выборка сделок, что и в дереве/штурвале дэшборда:
                        # window → категории symbol+family. Числа совпадают 1-в-1.
                        _alloc = get_dashboard_data(steering_cfg.lookback_days,
                                                    manage_connection=False)
                        _adeals = _alloc.get('trades_df') if _alloc else None








                        metrics = compute_categories(_adeals) if _adeals is not None else []


                        if metrics:
                            quotas_path = os.path.join(JOURNAL_DIR, steering_cfg.quotas_file)
                            prev_quotas = {}
                            if os.path.exists(quotas_path):
                                with open(quotas_path, 'r', encoding='utf-8') as f:
                                    prev_quotas = json.load(f)
                            new_quotas = calculate_steering_wheel_quotas(
                                metrics,
                                prev_quotas,
                                {
                                    'alpha': steering_cfg.alpha,
                                    'min_q': steering_cfg.min_q,
                                    'max_q': steering_cfg.max_q,
                                    'score_mode': steering_cfg.score_mode,
                                    'min_trades': steering_cfg.min_trades,
                                    'gamma': getattr(steering_cfg, 'gamma', 1.5),
                                    'score_volume_prior': getattr(steering_cfg, 'score_volume_prior', 0.0),
                    # Политика потерь (kill switch): порог в рублях, рублёвая риск-квота
                    'quota_rub': balance * risk_cfg.max_risk_pct,
                    'loss_decay': getattr(steering_cfg, 'loss_decay', 0.25),
                    'kill_pnl_pct': getattr(steering_cfg, 'kill_pnl_pct', 0.02),
                    'kill_pnl_rub': getattr(steering_cfg, 'kill_pnl_rub', 0.0),
                    'kill_min_trades': getattr(steering_cfg, 'kill_min_trades', 3),
                                    # если gamma ещё нет в cfg — подставим дефолт
                                }
                            )

                            with open(quotas_path, 'w', encoding='utf-8') as f:
                                json.dump(new_quotas, f, ensure_ascii=False, indent=2)

                            # тФАтФА ╨Я╤А╨╕╨╜╤В: Strategy Tree тЖТ ╨┐╨╡╤А╨╡╨║╨╗╨░╨┤╨║╨░ ╨╛╨▒╤К╤С╨╝╨░ тФАтФА
                            print(f"\n  [WHEEL] Пересчёт квот (score_mode={steering_cfg.score_mode}) "
                                  f"(окно {steering_cfg.lookback_days} дн.).", flush=True)
                            for _line in format_allocation_report(
                                    metrics, prev_quotas, new_quotas,
                                    steering_cfg.lookback_days,
                                    min_trades=steering_cfg.min_trades,
                                    score_mode=steering_cfg.score_mode):
                                print(_line, flush=True)
                            # Перекладка объёма: только стратегии без открытой позиции
                            # тФАтФА ╨Я╨╡╤А╨╡╨║╨╗╨░╨┤╨║╨░ ╨╗╨╛╤В╨╛╨▓: ╨Р╨С╨б╨Ю╨Ы╨о╨в╨Э╨л╨Щ ╤Ж╨╡╨╗╨╡╨▓╨╛╨╣ ╨╗╨╛╤В тФАтФА
                            # Раньше лот умножался на q_new/q_prev, поэтому стратегия с
                            # мелким лотом «догоняла» целевую долю множителем и тормозила
                            # перекладку. Теперь целевой лот считается от риск-квоты:
                            #     lot_i = (budget × q_i) / sl_money_i
                            # budget — свободная часть квоты (за вычетом риска уже открытых
                            # позиций), поэтому Σ(lot×sl_money) ≤ quota по построению.
                            risk_quota = balance * risk_cfg.max_risk_pct
                            _slm = {}
                            _used_risk = 0.0
                            _free_keys = []
                            _n_in_cat = {}
                            # Σ score свободных стратегий категории — доля внутри категории
                            # считается по score бэктеста, а не поровну (решение 19.10).
                            _score_sum_cat = {}
                            _sid_by_key = {}
                            for _k, _s in active_strategies.items():
                                _info = symbol_data.get(_s['symbol'], {}).get('info')
                                _m = _sl_money_per_lot(_s['symbol'], _info, _s.get('sl_points') or 0)
                                _slm[_k] = _m
                                _sid_by_key[_k] = record_category_id(_s)
                                if _s['position'] is not None:
                                    _used_risk += float(_s['lot']) * _m
                                else:
                                    _free_keys.append(_k)
                                    _n_in_cat[_sid_by_key[_k]] = _n_in_cat.get(_sid_by_key[_k], 0) + 1
                                    _score_sum_cat[_sid_by_key[_k]] = (
                                        _score_sum_cat.get(_sid_by_key[_k], 0.0)
                                        + max(float(_s.get('score') or 0.0), 0.0))
                            _q_covered = sum(new_quotas.get(_sid, 0.0) for _sid in set(_sid_by_key[_k] for _k in _free_keys))
                            _budget = max(0.0, risk_quota - _used_risk)
                            changed = 0
                            for key, s in active_strategies.items():
                                if s['position'] is not None:
                                    continue
                                sid = record_category_id(s)
                                q_new = new_quotas.get(sid)
                                if q_new is None:
                                    continue
                                _m = _slm.get(key, 0.0)

                                # Kill switch: категория убыточна (квота 0) → новые входы запрещены.
                                if q_new <= 0:
                                    if s.get('enabled', True) or float(s.get('lot') or 0) > 0:
                                        print(f"  [WHEEL] KILL {key}: q=0 → торговля остановлена "
                                              f"(категория {sid}, лот {s['lot']:.3f} → 0)", flush=True)
                                    s['lot'] = 0.0
                                    s['enabled'] = False
                                    s['disabled_reason'] = f'steering: квота категории {sid} = 0 (живой убыток)'
                                    st['killed'] += 1
                                    continue

                                # Возврат в работу: категория снова в плюсе
                                if s.get('enabled', True) is False:
                                    print(f"  [WHEEL] возврат в работу: {key} (категория {sid} снова в плюсе)", flush=True)
                                    s['enabled'] = True
                                    s.pop('disabled_reason', None)

                                if _m <= 0 or _budget <= 0 or _q_covered <= 0:
                                    continue
                                # Доля внутри категории — по score бэктеста (как в
                                # tree_weighted_lots); поровну — только если score категории 0.
                                _sc = max(float(s.get('score') or 0.0), 0.0)
                                _scat = _score_sum_cat.get(sid, 0.0)
                                _share = (_sc / _scat) if _scat > 0 else (1.0 / max(1, _n_in_cat.get(sid, 1)))
                                new_lot = _budget * (q_new / _q_covered) * _share / _m
                                _info = symbol_data.get(s['symbol'], {}).get('info')
                                _vol = _normalize_volume(new_lot, _info)
                                new_lot = max(_vol if _vol is not None else risk_cfg.min_lot,
                                              risk_cfg.min_lot)
                                if abs(new_lot - s['lot']) > 1e-9:
                                    print(f"  [STEERING] {key}: lot {s['lot']:.3f} -> {new_lot:.3f} "
                                          f"(q {q_new:.3f}, score {_sc:.2f}/{_scat:.2f}, риск {s['lot'] * _m:,.0f} -> "
                                          f"{new_lot * _m:,.0f} ₽)")
                                    s['lot'] = new_lot
                                    changed += 1
                            print(f"  [STEERING] Квоты обновлены: {len(new_quotas)} стратегий, "
                                  f"лоты скорректированы: {changed}", flush=True)
                            _DEAD_TILT_DUP = """  # дубль тильт-блока (мёртвая ветка if False) — живёт в run_steering_wheel
        # Объём уже переложен штурвалом — здесь он только масштабируется по лучшей/
        # худшей связке «пара + день выхода» за окно до 90 дней (tactic_tilt.py).
        # Идемпотентно: повторный вызов с тем же множителем второй раз ±20% не
        # начисляет (маркеры tilt_base/tilt_mult), а лот от штурвала — новый базис.
        try:
            import tactic_tilt as _tt
            if getattr(steering_cfg, 'tactic_tilt_enabled', True):
                st['tilt'] = _tt.apply_tactic_tilt(
                    list(active_strategies.values()), when=datetime.now(),
                    pct=getattr(steering_cfg, 'tactic_tilt_pct', 0.20),
                    window_days=getattr(steering_cfg, 'tactic_tilt_window_days', 90),
                    min_trades=getattr(steering_cfg, 'tactic_tilt_min_trades', 2),
                    weekday_only=getattr(steering_cfg, 'tactic_tilt_weekday_only', False),
                    min_lot=risk_cfg.min_lot, log=print)
                if st['tilt'].get('n_changed'):
                    st['changed'] += int(st['tilt']['n_changed'])
        except Exception as _tt_e:
        """

        # тФАтФА ╨г╨╜╨╕╤Д╨╕╨║╨░╤Ж╨╕╤П ╨╕╤Б╤В╨╛╤З╨╜╨╕╨║╨░ ╨╗╨╛╤В╨░ тФАтФА
                            # Штурвал правит active_strategies — это и есть бой. Чтобы
                            # дэшборд/active_state.json показывали РЕАЛЬНУЮ перекладку (а не
                            # дотюненный tree-weighting лот), переносим итог штурвала назад
                            # в план (active). После этого active == active_strategies.
                            _lot_by_key = {_k: _v.get('lot') for _k, _v in active_strategies.items()}
                            _synced = 0
                            for _r in active:
                                _rk = strategy_key(_r['symbol'], _r['param_key'],
                                                   _r.get('type', 'stoch'),
                                                   _r.get('parabolic_max'))
                                _nl = _lot_by_key.get(_rk)
                                if _nl is not None and abs(float(_nl) - float(_r.get('lot') or 0)) > 1e-9:
                                    _r['lot'] = _nl
                                    _synced += 1
                            if _synced:
                                print(f"  [STEERING] Лоты синхронизированы в план (active): {_synced}", flush=True)
                    except Exception as se:
                        print(f"\n[WARN] Ошибка штурвала: {se!r} — квоты не изменены", flush=True)
                write_active_state(active, active_strategies, balance, risk_cfg.max_risk_pct, JOURNAL_DIR)




                # --- обновляем night_reset.json после ночного перерасчёта ---
                _write_night_reset(night_reset_path, start_time, len(bt_cfg.symbols), len(all_results), ts=now)
                if _night_full_due:
                    # Маркер здесь НЕ ставим: его двигает только run_full_backtest и только
                    # при 100% покрытии плана. Раньше он ставился в этой точке безусловно —
                    # в async-ветке этот прогон вообще ничего не пересчитывал (реранк по
                    # чекпойнтам), а маркер сдвигался, и следующая ночь молча пропускалась.
                    print("  ℹ Маркер ПОЛНОГО пересчёта выставляет сам прогон "
                          "(только при 100% покрытии плана)", flush=True)

                yesterday = now.date() - timedelta(days=1)
                report = generate_daily_report(yesterday)

                # Свежий бэктест → штурвал обязан отработать в этом же цикле
                # (сбрасываем таймер, чтобы периодический вызов ниже не ждал interval_sec).
                last_steering = datetime.min
                print(f"  Готово: {len(all_results)} комбинаций, {len(active)} активных")

                # тФАтФА ╨Ш╤Б╤В╨╛╤А╨╕╤П ╤Б╨┤╨╡╨╗╨╛╨║ ╨▓ SQLite (trades_db): ╤И╨░╨│ 1 тАФ ╨╗╨╛╨║╨░╨╗╤М╨╜╨░╤П ╨╖╨░╨┐╨╕╤Б╤М тФАтФА
                # Fail-safe: любая ошибка БД не должна ронять пайплайн.
                try:
                    import trades_db
                    _ingest_start(days=3)     # тот же ФОН: добор не тормозит ночной блок
                except Exception as _tdb_err:
                    print(f"  [WARN] trades_db: {_tdb_err!r}", flush=True)

            # тФАтФА ╨и╤В╤Г╤А╨▓╨░╨╗: ╨Ю╨С╨п╨Ч╨Р╨в╨Х╨Ы╨м╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В, ╨Э╨Х ╨┐╤А╨╕╨▓╤П╨╖╨░╨╜ ╨║ ╨╜╨╛╤З╨╜╨╛╨╝╤Г ╨▒╤Н╨║╤В╨╡╤Б╤В╤Г тФАтФА
            # Раньше блок жил внутри `if should_run_backtest:` → если ночной прогон
            # был пропущен/упал, штурвал не работал вовсе. Теперь он отрабатывает
            # при старте, сразу после ночного пересчёта (там сбрасывается
            # last_steering) и далее каждые steering_cfg.interval_sec.
            _steering_every = int(getattr(steering_cfg, 'interval_sec', 3600) or 3600)
            if not steering_cfg.enabled:
                if last_steering != datetime.min:
                    print("  [WHEEL] ОТКЛЮЧЁН: steering_cfg.enabled=False — квоты/лоты "
                          "не пересчитываются (это единственная разрешённая причина).", flush=True)
                    last_steering = datetime.min
            elif (now - last_steering).total_seconds() >= _steering_every:
                last_steering = now
                _wheel_st = run_steering_wheel(
                    active_strategies, active, symbol_data, balance,
                    risk_cfg, steering_cfg, journal_dir=JOURNAL_DIR,
                    tag=f'(плановый, каждые {_steering_every // 60} мин)')
                if _wheel_st.get('changed') or _wheel_st.get('synced'):
                    write_active_state(active, active_strategies, balance,
                                       risk_cfg.max_risk_pct, JOURNAL_DIR)
                    last_state_write = now

            # Периодическое обновление баланса (раз в минуту)
            if (now - last_balance_refresh).total_seconds() >= 60:
                acc = mt5.account_info()
                if acc is not None:
                    balance = acc.balance
                    equity = acc.equity

                    if initial_equity is None:
                        initial_equity = equity
                        initial_equity_dt = now
                        print(f"  [INIT] Initial equity: {equity:.2f}")

                    if daily_start_balance is None or now.date() != daily_start_date:
                        daily_start_balance = balance
                        daily_start_dt = now
                        daily_start_date = now.date()
                        print(f"  [INIT] Daily start balance: {balance:.2f}")
                        daily_stop_notified = False  # новый день — лимит снова активен

                    last_balance_refresh = now

                    # тФАтФА ╨Я╤А╨╛╨▓╨╡╤А╨║╨░ 1: Daily stop-loss тФАтФА
                    if daily_start_balance is not None:
                        dl_ok, dl_pct, dl_reason = check_daily_loss_limit(
                            daily_start_balance, equity, risk_cfg.daily_loss_limit_pct,
                            cashflow=(_net_cashflow(daily_start_dt) if daily_start_dt else 0.0),
                        )
                        if not dl_ok:
                            # Сбой терминала (нет account_info) — позиции НЕ закрываем, ждём следующей проверки
                            if 'account_info not available' in dl_reason:
                                continue
                            # Печатаем [STOP] и закрываем позиции один раз за день
                            if daily_stop_notified:
                                continue
                            daily_stop_notified = True
                            _resume_dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                            print(f"\n  [STOP] Daily loss limit: {dl_reason} — торговля остановлена до {_resume_dt.strftime('%d.%m.%Y %H:%M')} (сброс дневного лимита в 00:00)")
                            for key, s in list(active_strategies.items()):
                                if s['position'] is not None:
                                    print(f"  -> Закрытие {key} по daily stop-loss")
                                    exit_price = close_order(s['symbol'], s['position']['ticket'],
                                                            s['position']['direction'], s['magic'], symbol_data)
                                    if exit_price is not None:
                                        _record_close(key, s, now, exit_price, 'daily_stop', symbol_data,
                                                     record_trade, journal_df, JOURNAL_FILE)
                            continue

                    # тФАтФА ╨Я╤А╨╛╨▓╨╡╤А╨║╨░ 2: Equity stop тФАтФА
                    if initial_equity is not None:
                        eq_ok, eq_dd, eq_reason = check_equity_stop(
                            equity, initial_equity, risk_cfg.equity_stop_pct,
                            cashflow=(_net_cashflow(initial_equity_dt) if initial_equity_dt else 0.0)
                        )
                        if not eq_ok:
                            print(f"\n  [STOP] Equity stop: {eq_reason} — аварийная остановка!")
                            for key, s in list(active_strategies.items()):
                                if s['position'] is not None:
                                    print(f"  -> Закрытие {key} по equity stop")
                                    exit_price = close_order(s['symbol'], s['position']['ticket'],
                                                            s['position']['direction'], s['magic'], symbol_data)
                                    if exit_price is not None:
                                        _record_close(key, s, now, exit_price, 'equity_stop', symbol_data,
                                                     record_trade, journal_df, JOURNAL_FILE)
                            raise RuntimeError(f"Equity stop triggered: {eq_reason}")

                    # тФАтФА ╨Я╤А╨╛╨▓╨╡╤А╨║╨░ 2b: Margin level (╨╖╨░╤Й╨╕╤В╨░ ╨╛╤В margin call тАФ ┬л╨░╨╣╤Б╨▒╨╡╤А╨│┬╗) тФАтФА
                    ml_status, ml_level, ml_reason = check_margin_level(
                        risk_cfg.min_margin_level_pct, risk_cfg.margin_level_stop_pct)
                    if ml_status == 'stop':
                        print(f"\n  [STOP] {ml_reason} — аварийное сокращение!")
                        for key, s in list(active_strategies.items()):
                            if s['position'] is not None:
                                print(f"  -> Закрытие {key} по margin level stop")
                                exit_price = close_order(s['symbol'], s['position']['ticket'],
                                                        s['position']['direction'], s['magic'], symbol_data)
                                if exit_price is not None:
                                    _record_close(key, s, now, exit_price, 'margin_stop', symbol_data,
                                                 record_trade, journal_df, JOURNAL_FILE)
                        raise RuntimeError(f"Margin level stop triggered: {ml_reason}")
                    elif ml_status == 'warn':
                        print(f"  [WARN] {ml_reason}", flush=True)

                    # тФАтФА ╨Я╤А╨╛╨▓╨╡╤А╨║╨░ 3: Realtime quota recalc тФАтФА
                    if risk_cfg.realtime_quota_recalc and (now - last_quota_recalc).total_seconds() >= risk_cfg.quota_recalc_interval_sec:
                        active_positions = []
                        for s in active_strategies.values():
                            if s['position'] is not None:
                                active_positions.append({
                                    'symbol': s['symbol'],
                                    'lot': s['position']['lot'],
                                    'sl_points': s['sl_points']
                                })
                        quota_ok, risk_pct, quota = realtime_quota_recalc(balance, active_positions, risk_cfg.max_risk_pct)
                        if not quota_ok:
                            print(f"  [WARN] Realtime quota exceeded: risk={risk_pct:.2f}% > quota тАФ "
                                  f"вход блокирует гейт квоты категории "
                                  f"(strategy_engine.quota_gate_check), здесь — только предупреждение")

            # Тики
            ticks = {}
            for sym in bt_cfg.symbols:
                try:
                    t = mt5.symbol_info_tick(sym)
                    if t is not None:
                        ticks[sym] = (t.bid, t.ask)
                except Exception as e:
                    print(f"\n[WARN] Ошибка получения тика {sym}: {e!r}", flush=True)

            if not ticks:
                idle_sec = (now - last_ticks_time).total_seconds()
                if (idle_sec >= bt_cfg.connection_timeout_sec
                        and (now - last_conn_warn_time).total_seconds() >= bt_cfg.connection_warn_every_sec):
                    print(f"\n[{now}] ВНИМАНИЕ: тиков нет уже {int(idle_sec // 60)} мин — "
                          f"проверь терминал (отключение/рынок закрыт).", flush=True)
                    last_conn_warn_time = now
                time.sleep(60 if is_weekend else bt_cfg.poll_interval)  # выходной — тиков нет, реже
                continue
            last_ticks_time = now

            # Обновление баров
            any_finalized = False
            for sym in ticks:
                if not is_weekend and sym in symbol_data:  # будни — обновляем бары; выходной — не обновляем
                    bid, ask = ticks[sym]
                    try:
                        if update_symbol_bar(sym, bid, ask, now):
                            any_finalized = True
                    except Exception as e:
                        print(f"\n[WARN] Ошибка обновления бара {sym}: {e!r}", flush=True)

            # Трейлинг-стоп (ATR chandelier) — независимо от стратегий
            try:
                trail_mgr.update(symbol_data, ticks)
            except Exception as e:
                print(f"\n[WARN] Ошибка трейлинг-стопа: {e!r}", flush=True)

            # Проверка сигналов — ТОЛЬКО в будни (Пн-Пт), рынок закрыт Сб-Вс
            if any_finalized and now.weekday() < 5:  # Пн=0 ... Пт=4
                try:
                    check_active_signals(
                        now, active_strategies, symbol_data,
                        calc_stochastic, check_exit_stoch, check_entry_stoch,
                        calc_parabolic, check_exit_parabolic, check_entry_parabolic,
                        calc_moving_average, check_exit_ma, check_entry_ma,
                        send_order, close_order, get_deal_exit_price,
                        _record_close, record_trade,
                        journal_df, JOURNAL_FILE,
                        calc_random_forest, check_exit_rf, check_entry_rf,
                        calc_logreg, check_exit_logreg, check_entry_logreg,
                        calc_macd_cross, check_exit_macd_cross, check_entry_macd_cross,
                        calc_rsi_reversal, check_exit_rsi_reversal, check_entry_rsi_reversal,
                        calc_bollinger, check_exit_bollinger, check_entry_bollinger,
                        calc_ema_crossover, check_exit_ema_crossover, check_entry_ema_crossover,
                        calc_rsi_divergence, check_exit_rsi_divergence, check_entry_rsi_divergence,
                        calc_ichimoku, check_exit_ichimoku, check_entry_ichimoku,
                        calc_zscore, check_exit_zscore, check_entry_zscore,
                        calc_autocorrelation, check_exit_autocorr, check_entry_autocorr,
                        calc_hurst, check_exit_hurst, check_entry_hurst,
                        calc_lr_channel, check_exit_lrc, check_entry_lrc,
                        calc_percentile, check_exit_percentile, check_entry_percentile,
                        calc_runs_test, check_exit_runs, check_entry_runs,
                        calc_cointegration, check_exit_coint, check_entry_coint,
                        calc_rolling_sharpe, check_exit_sharpe, check_entry_sharpe,
                        calc_skewness, check_exit_skewness, check_entry_skewness,
                        calc_bayesian_trend, check_exit_bayesian, check_entry_bayesian,
                        calc_kurtosis, check_exit_kurtosis, check_entry_kurtosis,
                        calc_chi_square, check_exit_chi_square, check_entry_chi_square,
                        calc_vwap, check_exit_vwap, check_entry_vwap,
                        calc_momentum, check_exit_momentum, check_entry_momentum,
                        calc_pin_bar, check_exit_pin_bar, check_entry_pin_bar,
                        calc_prev_daily_direction, check_exit_prev_daily, check_entry_prev_daily,
                        calc_rolling_correlation, check_exit_corr, check_entry_corr,
                        calc_williams_r, check_exit_williams_r, check_entry_williams_r,
                        calc_macd_histogram, check_exit_macd_histogram, check_entry_macd_histogram,
                        calc_bb_squeeze, check_exit_bb_squeeze, check_entry_bb_squeeze,
                        calc_donchian, check_exit_donchian, check_entry_donchian,
                        calc_engulfing, check_exit_engulfing, check_entry_engulfing,
                        calc_cci, check_exit_cci, check_entry_cci,
                        calc_supertrend, check_exit_supertrend, check_entry_supertrend,
                        calc_adx, check_exit_adx, check_entry_adx,
                        calc_obv, check_exit_obv, check_entry_obv,
                        calc_morning_evening_star, check_exit_morning_evening_star, check_entry_morning_evening_star,
                        risk_cfg=risk_cfg,
                    )
                except Exception as e:
                    print(f"\n[WARN] Ошибка проверки сигналов: {e!r}", flush=True)

            # Обновление active_state.json примерно раз в минуту
            if (now - last_state_write).total_seconds() >= 60:
                write_active_state(active, active_strategies, balance, risk_cfg.max_risk_pct, JOURNAL_DIR)



                last_state_write = now

            # Смена месяца → новый файл журнала
            if now.strftime('%Y%m') != journal_month:
                save_journal(journal_df, JOURNAL_FILE)
                journal_month = now.strftime('%Y%m')
                JOURNAL_FILE = os.path.join(JOURNAL_DIR, f"journal_{journal_month}.csv")
                journal_df = load_journal(JOURNAL_FILE, COLUMNS)
                print(f"\n[{now}] Новый журнал: {JOURNAL_FILE}", flush=True)

            # Периодическое сохранение журнала
            if (now - last_journal_write).total_seconds() >= bt_cfg.journal_save_every_sec:
                save_journal(journal_df, JOURNAL_FILE)
                last_journal_write = now

            # Статус — компактная агрегированная статистика
            active_pos = sum(1 for s in active_strategies.values() if s['position'] is not None)
            bar_time = '??'
            if bt_cfg.symbols and bt_cfg.symbols[0] in symbol_data:
                bar_time = symbol_data[bt_cfg.symbols[0]]['current_hour'].strftime('%H:%M')

            stats = defaultdict(lambda: defaultdict(int))
            for key, s in active_strategies.items():
                sym = s['symbol']
                stype = s.get('type', 'stoch')
                stats[sym][stype] += 1

            sym_stats = []
            for sym in bt_cfg.symbols:
                if sym in stats:
                    type_counts = [f"{t[0].upper()}({c})" for t, c in sorted(stats[sym].items())]
                    sym_stats.append(f"{get_non_usd(sym)}:{','.join(type_counts)}")

            status_str = ' | '.join(sym_stats) if sym_stats else 'нет активных'
            # print(f"\r[{now.strftime('%H:%M:%S')}] бар {bar_time} | "
            #       f"активных {len(active_strategies)} | позиций {active_pos} | "
            #       f"{status_str} | ждём...", end='', flush=True)

            time.sleep(60 if is_weekend else bt_cfg.poll_interval)  # выходной — тиков нет, реже

    except KeyboardInterrupt:
        print("\nОстановка по Ctrl+F2...")

    except Exception as exc:
        print(f"\n[КРИТИЧНО] Аварийная остановка: {exc!r}", flush=True)
        raise

    finally:
        save_journal(journal_df, JOURNAL_FILE)
        write_active_state(active, active_strategies, balance, risk_cfg.max_risk_pct, JOURNAL_DIR)



        try:
            mt5.shutdown()
        except Exception:
            pass



        print("Журнал и состояние сохранены. Терминал отключён.")
