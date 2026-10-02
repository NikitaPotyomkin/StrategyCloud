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

from functions import terminal_on, run_full_backtest, _checkpoint_dir
from daily_report import generate_daily_report, generate_missing_reports
from trail_manager import TrailManager
from wheel import calculate_steering_wheel_quotas, build_metrics_from_journal
from risk_manager import (
    calc_metrics, composite_score, distribute_lots, check_integration_budget,
    check_daily_loss_limit, check_equity_stop, realtime_quota_recalc,
    MAX_COMBOS_PER_STRATEGY,
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


# ═══ Утилита: запись night_reset.json (первый прогон + каждый ночной перерасчёт) ═══
def _write_night_reset(night_reset_path, start_time, symbols_count, results_count, ts=None):
    """Записывает night_reset.json — и при первом прогоне, и каждую ночь."""
    if ts is None:
        ts = datetime.now()
    fake_timestamp = ts.replace(hour=3, minute=0, second=0, microsecond=0)
    with open(night_reset_path, 'w', encoding='utf-8') as f:
        json.dump({
            'started_at': start_time.isoformat(),
            'timestamp': fake_timestamp.isoformat(),
            'status': 'completed',
            'symbols': symbols_count,
            'total_results': results_count,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  ✅ night_reset.json записан ({fake_timestamp.strftime('%H:%M')}) — старт: {start_time}")


if __name__ == '__main__':
    start_time = datetime.now()
    print(f"🚀 ЗАПУСК СИСТЕМЫ: {start_time.strftime('%H:%M:%S')}")

    # ═══ КОНФИГУРАЦИЯ (единый источник — config.py) ═══
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

    # ═══ ВЫЧИСЛИТЕЛЬНЫЙ БЮДЖЕТ ═══
    def _combo(*args):
        result = 1
        for a in args:
            result *= a
        return result

    sp = strategy_params
    integration_budgets_dict = {
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

    # ═══ ПОДКЛЮЧЕНИЕ ═══
    terminal_on('demo')
    os.makedirs(JOURNAL_DIR, exist_ok=True)

    # ═══ ЗАГРУЗКА ИСТОРИИ ═══
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
            print(f"   • {sym}")

    # ═══ ЖУРНАЛ ═══
    journal_df = load_journal(JOURNAL_FILE, COLUMNS)

    # ═══ АКТИВНЫЕ СТРАТЕГИИ ═══
    active_strategies = {}

    # ═══ ГЕНЕРАЦИЯ ПРОПУЩЕННЫХ ОТЧЁТОВ ═══
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

    # ═══ ПЕРВЫЙ РАСЧЁТ ═══
    print("\nБэктест (первый расчёт)...")

    FORCE_RECALC = bt_cfg.force_recalc
    night_reset_path = os.path.join(_checkpoint_dir(), 'night_reset.json')
    is_first_run = not os.path.exists(night_reset_path)
    manual_full = bool(bt_cfg.full_recalc_mode)   # ручной полный пересчёт при запуске
    
    # ═══ АВТОМАТИЧЕСКИЙ ПЕРЕСЧЁТ ПОСЛЕ ЗАКРЫТИЯ РЫНКА (Сб 00:00) ═══
    now = datetime.now()
    if bt_cfg.auto_weekend_recalc:
        # Проверяем, наступила ли суббота после пятницы
        if now.weekday() == 5 and now.hour == 0:  # Суббота 00:00+
            FORCE_RECALC = True
            print(f"  🌙 АВТОМАТИЧЕСКИЙ force_recalc после закрытия рынка ({now.strftime('%Y-%m-%d %H:%M')})")
        elif now.weekday() == 5 and now.hour > 0:
            # Суббота уже прошла полночь — force_recalc не нужен (уже был в 00:00)
            pass

    if manual_full:
        print("  ⚙️  full_recalc_mode=True — РУЧНОЙ ПОЛНЫЙ ПЕРЕСЧЁТ всех стратегий")
    elif is_first_run:
        print("  🌙 night_reset.json не найден — первый прогон, полный пересчёт")
    else:
        print("  ✅ night_reset.json найден — используем чекпоинты (лайт-режим)")

    try:
        all_top, all_results = run_full_backtest(
            bt_cfg.symbols, symbol_data, strategy_params, bt_cfg,
            test_strategy=None,
            test_mode=False,
            force_recalc=FORCE_RECALC,
            incremental=True,
            is_night_run=is_first_run or manual_full
        )

        # После первого прогона записываем night_reset.json
        if is_first_run or manual_full:
            _write_night_reset(night_reset_path, start_time, len(bt_cfg.symbols), len(all_results))

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
                             risk_cfg.max_risk_pct, risk_cfg.min_lot, risk_cfg.min_score)

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

    write_active_state(active, active_strategies, balance, risk_cfg.max_risk_pct, JOURNAL_DIR)

    print(f"\nЗапуск цикла. Ctrl+F2 для остановки.\n")

    # ═══ ГЛАВНЫЙ ЦИКЛ ═══
    last_full_backtest_date = datetime.now().date()
    last_mode_check = datetime.now().date()
    last_state_write = datetime.now()
    last_journal_write = datetime.now()
    journal_month = datetime.now().strftime('%Y%m')
    last_ticks_time = datetime.now()
    last_conn_warn_time = datetime.min
    last_balance_refresh = datetime.now()
    last_quota_recalc = datetime.now()
    initial_equity = None
    daily_start_balance = None
    daily_start_date = None

    try:
        while True:
            now = datetime.now()

            # Смена дня
            if now.date() != last_mode_check:
                last_mode_check = now.date()
                print(f"\n[{now}] Новый день")

            # Ночной пересчёт: раз в сутки с 3:00
            # Пт 3:00 — последний пересчёт перед выходными
            # Сб 3:00 — если auto_weekend_recalc=True, был force_recalc в 00:00, теперь лайт
            # Вс 3:00 — пропускаем (рынок закрыт)
            # Пн 3:00 — новый пересчёт
            is_weeknight = now.weekday() < 5  # Пн-Пт
            is_saturday = now.weekday() == 5
            
            if now.hour >= bt_cfg.night_backtest_hour and now.date() != last_full_backtest_date:
                
                # Пропускаем Вс и Сб (рынок закрыт)
                if is_saturday:
                    print(f"\n[{now.strftime('%H:%M:%S')}] ⏸ Суббота — пересчёт пропущен (рынок закрыт)")
                    last_full_backtest_date = now.date()
                    continue
                
                print(f"\n[{now.strftime('%H:%M:%S')}] Ночной перерасчёт...")

                try:
                    _, all_results = run_full_backtest(
                        bt_cfg.symbols, symbol_data, strategy_params, bt_cfg,
                        test_strategy=None,
                        test_mode=False,
                        force_recalc=False,
                        is_night_run=False
                    )
                except Exception as exc:
                    print(f"\n[WARN] Ночной перерасчёт не удался: {exc!r} — "
                          f"оставляем текущие стратегии, повторим завтра в 3:00.", flush=True)
                    continue
                last_full_backtest_date = now.date()
                acc = mt5.account_info()
                balance = acc.balance if acc else 1_000_000
                deduped_results = all_results
                active = distribute_lots(deduped_results, symbol_data, balance,
                                         risk_cfg.max_risk_pct, risk_cfg.min_lot, risk_cfg.min_score)
                print(f"Баланс: {balance:.0f} руб | Квота: {balance * risk_cfg.max_risk_pct:.0f} руб | "
                      f"Активировано {len(active)} из {len(deduped_results)} (всего {len(all_results)})")

                write_ranking(active, all_results, JOURNAL_DIR, bt_cfg.backtest_days, len(active), None)
                sync_active_strategies(active, now, symbol_data, active_strategies,
                                       close_order, get_deal_exit_price, record_trade,
                                       strategy_key, assign_magic, bt_cfg.magic_base, len(active))

                # ── Штурвал: плавное перераспределение квот по реальным сделкам ──
                if steering_cfg.enabled:
                    try:
                        metrics = build_metrics_from_journal(journal_df, n_last=steering_cfg.n_last_trades)
                        if metrics:
                            quotas_path = os.path.join(JOURNAL_DIR, steering_cfg.quotas_file)
                            prev_quotas = {}
                            if os.path.exists(quotas_path):
                                with open(quotas_path, 'r', encoding='utf-8') as f:
                                    prev_quotas = json.load(f)
                            new_quotas = calculate_steering_wheel_quotas(
                                metrics, prev_quotas,
                                alpha=steering_cfg.alpha,
                                min_q=steering_cfg.min_q,
                                max_q=steering_cfg.max_q,
                                min_trades=steering_cfg.min_trades,
                                max_dd=steering_cfg.max_dd,
                            )
                            with open(quotas_path, 'w', encoding='utf-8') as f:
                                json.dump(new_quotas, f, ensure_ascii=False, indent=2)
                            # Плавная корректировка лотов активных стратегий без открытых позиций
                            n_act = max(len(active_strategies), 1)
                            changed = 0
                            for key, s in active_strategies.items():
                                if s['position'] is not None:
                                    continue
                                sid = f"{s['symbol']}_{s['param_key']}"
                                q_new = new_quotas.get(sid)
                                if q_new is None:
                                    continue
                                q_prev = prev_quotas.get(sid, 1.0 / n_act)
                                factor = q_new / q_prev if q_prev > 0 else 1.0
                                new_lot = max(risk_cfg.min_lot, s['lot'] * factor)
                                if abs(new_lot - s['lot']) > 1e-9:
                                    print(f"  [STEERING] {key}: lot {s['lot']:.3f} -> {new_lot:.3f} "
                                          f"(q {q_prev:.3f} -> {q_new:.3f})")
                                    s['lot'] = new_lot
                                    changed += 1
                            print(f"  [STEERING] Квоты обновлены: {len(new_quotas)} стратегий, "
                                  f"лоты скорректированы: {changed}", flush=True)
                    except Exception as se:
                        print(f"\n[WARN] Ошибка штурвала: {se!r} — квоты не изменены", flush=True)
                write_active_state(active, active_strategies, balance, risk_cfg.max_risk_pct, JOURNAL_DIR)

                # --- обновляем night_reset.json после ночного перерасчёта ---
                _write_night_reset(night_reset_path, start_time, len(bt_cfg.symbols), len(all_results), ts=now)

                yesterday = now.date() - timedelta(days=1)
                report = generate_daily_report(yesterday)

                print(f"  Готово: {len(all_results)} комбинаций, {len(active)} активных")

            # Периодическое обновление баланса (раз в минуту)
            if (now - last_balance_refresh).total_seconds() >= 60:
                acc = mt5.account_info()
                if acc is not None:
                    balance = acc.balance
                    equity = acc.equity

                    if initial_equity is None:
                        initial_equity = equity
                        print(f"  [INIT] Initial equity: {equity:.2f}")

                    if daily_start_balance is None or now.date() != daily_start_date:
                        daily_start_balance = balance
                        daily_start_date = now.date()
                        print(f"  [INIT] Daily start balance: {balance:.2f}")

                    last_balance_refresh = now

                    # ── Проверка 1: Daily stop-loss ──
                    if daily_start_balance is not None:
                        dl_ok, dl_pct, dl_reason = check_daily_loss_limit(
                            daily_start_balance, equity, risk_cfg.daily_loss_limit_pct
                        )
                        if not dl_ok:
                            print(f"\n  [STOP] Daily loss limit: {dl_reason} — остановка торговли!")
                            for key, s in list(active_strategies.items()):
                                if s['position'] is not None:
                                    print(f"  -> Закрытие {key} по daily stop-loss")
                                    exit_price = close_order(s['symbol'], s['position']['ticket'],
                                                            s['position']['direction'], s['magic'], symbol_data)
                                    if exit_price is not None:
                                        _record_close(key, s, now, exit_price, 'daily_stop', symbol_data,
                                                     record_trade, journal_df, JOURNAL_FILE)
                            continue

                    # ── Проверка 2: Equity stop ──
                    if initial_equity is not None:
                        eq_ok, eq_dd, eq_reason = check_equity_stop(equity, initial_equity, risk_cfg.equity_stop_pct)
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

                    # ── Проверка 3: Realtime quota recalc ──
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
                            print(f"  [WARN] Realtime quota exceeded: risk={risk_pct:.2f}% > quota — "
                                  f"новые ордера не открываются до пересчёта в 3:00")

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
                time.sleep(bt_cfg.poll_interval)
                continue
            last_ticks_time = now

            # Обновление баров
            any_finalized = False
            for sym in ticks:
                if sym in symbol_data:
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

            # Проверка сигналов
            if any_finalized:
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

            time.sleep(bt_cfg.poll_interval)

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
