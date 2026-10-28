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

# ╨Ы╨╛╨│╨╕╤А╨╛╨▓╨░╨╜╨╕╨╡ ╨┐╤А╨╛╨│╨╛╨╜╨░ ╨▓ journals/run.log (stdout+stderr ╤Б ╤А╨╛╤В╨░╤Ж╨╕╨╡╨╣).
# Fail-safe: ╨╗╤О╨▒╨░╤П ╨┐╤А╨╛╨▒╨╗╨╡╨╝╨░ ╤Б ╨╗╨╛╨│╨╛╨╝ ╨╜╨╡ ╨┤╨╛╨╗╨╢╨╜╨░ ╤А╨╛╨╜╤П╤В╤М ╨┐╨░╨╣╨┐╨╗╨░╨╣╨╜.
try:
    import run_log
    try:
        run_log.setup()
    except Exception:
        # ╨Э╨╡ ╨│╨╗╤Г╤И╨╕╨╝ ╨╝╨╛╨╗╤З╨░: ╨▒╨╡╨╖ ╤Д╨░╨╣╨╗╨╛╨▓╨╛╨│╨╛ ╨╗╨╛╨│╨░ ╨▓╨╡╤Б╤М ╨┐╤А╨╛╨│╨╛╨╜ ╨╜╨╡ ╨╛╤Б╤В╨░╨▓╨╕╤В ╤Б╨╗╨╡╨┤╨╛╨▓ ╨▓ journals/.
        import sys as _sys
        print(f"[WARN] ╨Ы╨╛╨│ journals/run.log ╨╜╨╡ ╨╛╤В╨║╤А╤Л╨╗╤Б╤П ({_sys.exc_info()[1]!r}) тАФ "
              f"╨┐╤А╨╛╨│╨╛╨╜ ╨┐╤А╨╛╨┤╨╛╨╗╨╢╨╕╤В╤Б╤П ╨▒╨╡╨╖ ╤Д╨░╨╣╨╗╨╛╨▓╨╛╨│╨╛ ╨╗╨╛╨│╨░", flush=True)
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
    calc_metrics, composite_score, distribute_lots, check_integration_budget,
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
    """╨Ч╨░╨┐╨╕╤Б╤Л╨▓╨░╨╡╤В night_reset.json тАФ ╨╕ ╨┐╤А╨╕ ╨┐╨╡╤А╨▓╨╛╨╝ ╨┐╤А╨╛╨│╨╛╨╜╨╡, ╨╕ ╨║╨░╨╢╨┤╤Г╤О ╨╜╨╛╤З╤М."""
    if ts is None:
        ts = datetime.now()
    # timestamp тАФ ╨а╨Х╨Р╨Ы╨м╨Э╨Ю╨Х ╨▓╤А╨╡╨╝╤П ╨╖╨░╨┐╨╕╤Б╨╕ ╨╝╨░╤А╨║╨╡╤А╨░. ╨а╨░╨╜╤М╤И╨╡ ╤Б╤О╨┤╨░ ╨┐╤А╨╕╨╜╤Г╨┤╨╕╤В╨╡╨╗╤М╨╜╨╛ ╨┐╨╕╤Б╨░╨╗╨╕
    # 03:00 (fake_timestamp), ╨╕ ╨┐╨╛ ╨╝╨░╤А╨║╨╡╤А╤Г ╨╜╨╡╨╗╤М╨╖╤П ╨▒╤Л╨╗╨╛ ╨┐╨╛╨╜╤П╤В╤М, ╨║╨╛╨│╨┤╨░ ╨┐╤А╨╛╨│╨╛╨╜ ╨▒╤Л╨╗ ╨╜╨░
    # ╤Б╨░╨╝╨╛╨╝ ╨┤╨╡╨╗╨╡: ╨╛╤Б╤В╨░╨▓╨░╨╗╨╛╤Б╤М ╤В╨╛╨╗╤М╨║╨╛ ╨│╨░╨┤╨░╤В╤М ╨┐╨╛ ╨▓╤А╨╡╨╝╨╡╨╜╨╕ ╨┐╨╡╤А╨╡╨╖╨░╨┐╤Г╤Б╨║╨░ ╨┐╤А╨╛╤Ж╨╡╤Б╤Б╨░.
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
    print(f"\n  тЬЕ ╨Ь╨░╤А╨║╨╡╤А ╨┐╤А╨╛╨│╨╛╨╜╨░ ╨╖╨░╨┐╨╕╤Б╨░╨╜ ({ts.strftime('%Y-%m-%d %H:%M')}, "
          f"╨╜╨╛╤З╨╜╨╛╨╡ ╨╛╨║╨╜╨╛ {night_window.strftime('%H:%M')}) тАФ ╤Б╤В╨░╤А╤В: {start_time}")


# тХРтХРтХР ╨г╤В╨╕╨╗╨╕╤В╨░: ╨╝╨░╤А╨║╨╡╤А ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╡╨│╨╛ ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ (╨┐╤А╨░╨▓╨╕╨╗╨╛ ┬л╨╜╨╡ ╤З╨░╤Й╨╡, ╤З╨╡╨╝ ╤А╨░╨╖ ╨▓ N ╨┤╨╜╨╡╨╣┬╗) тХРтХРтХР
def _read_last_full_recalc(marker_path):
    """╨Ф╨░╤В╨░ ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╡╨│╨╛ ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ тАФ ╨в╨Ю╨Ы╨м╨Ъ╨Ю ╨╕╨╖ ╨╝╨░╤А╨║╨╡╤А╨░ last_full_recalc.json."""
    try:
        with open(marker_path, 'r', encoding='utf-8') as f:
            ts = json.load(f).get('last_full_recalc', '')
        if ts:
            return datetime.fromisoformat(ts).date()
    except (OSError, ValueError, json.JSONDecodeError):
        pass



    # ╨д╨╛╨╗╨▒╤Н╨║ (╨╝╨░╤А╨║╨╡╤А╨░ ╨╡╤Й╤С ╨╜╨╡╤В, ╨╜╨░╨┐╤А. ╤Б╤А╨░╨╖╤Г ╨┐╨╛╤Б╨╗╨╡ ╨╛╨▒╨╜╨╛╨▓╨╗╨╡╨╜╨╕╤П): ╤Б╨░╨╝╨░╤П ╤Б╨▓╨╡╨╢╨░╤П ╨┤╨░╤В╨░ ╨╕╨╖
    # night_reset.json ╨╕ mtime ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨╛╨▓ тАФ ╤З╤В╨╛╨▒╤Л ╨Э╨Х ╨╖╨░╨┐╤Г╤Б╨║╨░╤В╤М ╨╗╨╕╤И╨╜╨╕╨╣ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В.
    _dates = []
    try:
        # night_reset.json ╨╕╤Б╤В╨╛╤З╨╜╨╕╨║╨╛╨╝ ╨┤╨░╤В╤Л ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ ╨Э╨Х ╤П╨▓╨╗╤П╨╡╤В╤Б╤П: ╨╡╨│╨╛ ╨┐╨╡╤А╨╡╨╖╨░╨┐╨╕╤Б╤Л╨▓╨░╤О╤В
        # ╨╕ ╨╜╨╛╤З╨╜╤Л╨╡ ╤А╨╡╤А╨░╨╜╨║╨╕ (03:00 ╨║╨░╨╢╨┤╤Л╨╣ ╨┤╨╡╨╜╤М). ╨Ш╨╖-╨╖╨░ ╤Н╤В╨╛╨│╨╛ ┬л╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╕╨╣ ╨┐╨╛╨╗╨╜╤Л╨╣┬╗ ╨▓╤Л╨│╨╗╤П╨┤╨╡╨╗ ╨║╨░╨║
        # ╤Б╨╡╨│╨╛╨┤╨╜╤П╤И╨╜╨╕╨╣, ╨╕ ╨┐╨╡╤А╨▓╤Л╨╣ ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╛╤В╨║╨╗╨░╨┤╤Л╨▓╨░╨╗╤Б╤П ╨╜╨░ ╤Б╤Г╤В╨║╨╕. ╨Ю╤Б╤В╨░╤С╤В╤Б╤П ╤В╨╛╨╗╤М╨║╨╛
        # mtime ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨╛╨▓ ╤Б╨╕╨╝╨▓╨╛╨╗╨╛╨▓ тАФ ╨╕╤Е ╨┐╨╕╤И╨╡╤В ╤А╨╡╨░╨╗╤М╨╜╤Л╨╣ ╤А╨░╤Б╤З╤С╤В.
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



    # ╨Ф╨░╤В╤Г ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ ╨▒╨╡╤А╤С╨╝ ╨в╨Ю╨Ы╨м╨Ъ╨Ю ╨╕╨╖ ╨╝╨░╤А╨║╨╡╤А╨░ last_full_recalc.json.
    # mtime ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨╛╨▓ ╨╕ night_reset.json ╨┤╨░╨▓╨░╨╗╨╕ ╤Д╨░╨╗╤М╤И╨╕╨▓╨╛╨╡ ┬л╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╕╨╣ ╨┐╨╛╨╗╨╜╤Л╨╣ = ╤Б╨╡╨│╨╛╨┤╨╜╤П┬╗
    # ╨╕ ╨╝╨╛╨╗╤З╨░ ╨╛╤В╨║╨╗╨░╨┤╤Л╨▓╨░╨╗╨╕ ╨╜╨░╤Б╤В╨╛╤П╤Й╨╕╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╜╨░ ╤Б╤Г╤В╨║╨╕. ╨Э╨╡╤В ╨╝╨░╤А╨║╨╡╤А╨░ тЖТ ╨┤╨░╤В╨░ ╨╜╨╡╨╕╨╖╨▓╨╡╤Б╤В╨╜╨░ тЖТ
    # _full_recalc_due() ╤Б╤З╨╕╤В╨░╨╡╤В ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╜╤Г╨╢╨╜╤Л╨╝.
    return None


def _full_recalc_due(now, marker_path, gap_days, is_first_run=False, daily=False):
    """╨Я╨╛╤А╨░ ╨╗╨╕ ╨┤╨╡╨╗╨░╤В╤М ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В. ╨Т╨╛╨╖╨▓╤А╨░╤Й╨░╨╡╤В (due, days_since_full, last_full_date).

    ╨Я╤А╨░╨▓╨╕╨╗╨╛: ╨╛╨┤╨╕╨╜ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╜╨░ ┬л╨╛╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е┬╗ (╨б╨▒тАУ╨Т╤Б). ╨Ю╨║╨╜╨╛ ╨╛╨┐╤А╨╡╨┤╨╡╨╗╤П╨╡╤В╤Б╤П ╨┐╨╛ ╤Б╤Г╨▒╨▒╨╛╤В╨╡:
    ╨┤╨╗╤П ╨б╨▒/╨Т╤Б тАФ ╤В╨╡╨║╤Г╤Й╨╡╨╡, ╨┤╨╗╤П ╨Я╨╜тАУ╨Я╤В тАФ ╨┐╤А╨╛╤И╨╡╨┤╤И╨╡╨╡. ╨Х╤Б╨╗╨╕ ╨▓ ╨╛╨║╨╜╨╡ ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨╜╨╡ ╨▒╤Л╨╗╨╛ (╤Г╨╕╨║-╤Н╨╜╨┤ ╨┐╤А╨╛╨┐╤Г╤Й╨╡╨╜),
    ╨┤╨╛╨│╨╛╨╜╤П╨╡╨╝ ╨┐╤А╨╕ ╨┐╨╡╤А╨▓╨╛╨╝ ╨╢╨╡ ╨╖╨░╨┐╤Г╤Б╨║╨╡/╨╜╨╛╤З╨╜╨╛╨╝ ╨┐╤А╨╛╨│╨╛╨╜╨╡, ╨╜╨╛ ╨╜╨╡ ╤А╨░╨╜╤М╤И╨╡, ╤З╨╡╨╝ ╤З╨╡╤А╨╡╨╖ gap_days ╨┤╨╜╨╡╨╣
    ╨┐╨╛╤Б╨╗╨╡ ╨┐╤А╨╛╤И╨╗╨╛╨│╨╛ ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю (╨╖╨░╤Й╨╕╤В╨░ ╨╛╤В ╨╗╨╕╤И╨╜╨╕╤Е ╨┐╨╛╨▓╤В╨╛╤А╨╛╨▓).
    """
    last_full_date = _read_last_full_recalc(marker_path)
    days_since = (now.date() - last_full_date).days if last_full_date else None
    if is_first_run or last_full_date is None:
        return True, days_since, last_full_date
    anchor = now.date() - timedelta(days=(now.weekday() - 5) % 7)  # ╤Б╤Г╨▒╨▒╨╛╤В╨░ ╤В╨╡╨║╤Г╤Й╨╡╨│╨╛/╨┐╤А╨╛╤И╨╡╨┤╤И╨╡╨│╨╛ ╨╛╨║╨╜╨░
    in_window = last_full_date >= anchor
    gap_ok = (days_since is None) or (days_since >= gap_days)
    if daily:
        # full_recalc_daily=True: ╨╛╨▒╨╜╨╛╨▓╨╗╤П╨╡╨╝ ╨Т╨б╨о ╨║╨╛╤А╨╖╨╕╨╜╤Г ╨║╨░╨╢╨┤╤Г╤О ╨╜╨╛╤З╤М тАФ ╨╛╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е
        # ╨╜╨╡ ╤Г╤З╨╕╤В╤Л╨▓╨░╨╡╨╝, ╨╛╤Б╤В╨░╤С╤В╤Б╤П ╤В╨╛╨╗╤М╨║╨╛ ╨╖╨░╤Й╨╕╤В╨░ ╨╛╤В ╨┐╨╛╨▓╤В╨╛╤А╨╛╨▓ (gap_days).
        return gap_ok, days_since, last_full_date
    return (not in_window) and gap_ok, days_since, last_full_date


def _has_open_positions(magic_min=770000, magic_max=869999):
    """╨Х╤Б╤В╤М ╨╗╨╕ ╨Э╨Р╨и╨Ш ╨╛╤В╨║╤А╤Л╤В╤Л╨╡ ╨┐╨╛╨╖╨╕╤Ж╨╕╨╕ (magic ╨▓ ╨▒╨╛╨╡╨▓╨╛╨╝ ╨┤╨╕╨░╨┐╨░╨╖╨╛╨╜╨╡).

    ╨Э╤Г╨╢╨╜╨╛ ╨┤╨╗╤П ╤А╨╡╤И╨╡╨╜╨╕╤П ╨╛ ╨┐╨╛╨╗╨╜╨╛╨╝ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨╡: ╨▓ ╤Б╨╕╨╜╤Е╤А╨╛╨╜╨╜╨╛╨╝ ╤А╨╡╨╢╨╕╨╝╨╡, ╨┐╨╛╨║╨░ ╨╛╨╜ ╨╕╨┤╤С╤В (150тАУ230 ╨╝╨╕╨╜),
    ╨╜╨╡ ╨╖╨░╨┐╤Г╤Й╨╡╨╜, ╤В╨╛ ╨╡╤Б╤В╤М ╨▒╨░╤А╤Л, ╤Б╨╕╨│╨╜╨░╨╗╤Л, ╤В╤А╨╡╨╣╨╗╨╕╨╜╨│ ╨╕ ╨░╨▓╨░╤А╨╕╨╣╨╜╤Л╨╡ ╨╖╨░╤Й╨╕╤В╤Л ╨╜╨╡ ╨┐╤А╨╛╨▓╨╡╤А╤П╤О╤В╤Б╤П.
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
    """╨Ф╨╛╨┐╤Г╤Б╤В╨╕╨╝ ╨╗╨╕ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╤Б╨╡╨╣╤З╨░╤Б: ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╨╡ тАФ ╨▓╤Б╨╡╨│╨┤╨░, ╨▒╤Г╨┤╨╜╨╕ тАФ ╤В╨╛╨╗╤М╨║╨╛ ╨▓ ╨╜╨╛╤З╨╜╨╛╨╝ ╨╛╨║╨╜╨╡.

    ╨Ф╨╜╤С╨╝ ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╤А╨╛╤Е╨╛╨┤ (150тАУ230 ╨╝╨╕╨╜) ╨╖╨░╨▒╨╗╨╛╨║╨╕╤А╨╛╨▓╨░╨╗ ╨▒╤Л ╨▒╨╛╨╡╨▓╨╛╨╣ ╤Ж╨╕╨║╨╗ ╨╜╨░ ╤Б╨░╨╝╨╛╨╡ ╨░╨║╤В╨╕╨▓╨╜╨╛╨╡
    ╨▓╤А╨╡╨╝╤П, ╨┐╨╛╤Н╤В╨╛╨╝╤Г ╨┤╨╜╨╡╨▓╨╜╤Л╨╡ ╤Б╤В╨░╤А╤В╤Л ╨╕╨┤╤Г╤В ╨┐╨╛ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╨╝, ╨░ ╨╛╨▒╨╜╨╛╨▓╨╗╨╡╨╜╨╕╨╡ ╤Г╤Е╨╛╨┤╨╕╤В ╨▓ ╨╜╨╛╤З╤М.
    """
    if now.weekday() >= 5:
        return True
    return start_hour <= now.hour < end_hour


def _write_full_recalc_marker(marker_path, ts=None):
    """╨д╨╕╨║╤Б╨╕╤А╤Г╨╡╤В ╨┤╨░╤В╤Г ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╡╨│╨╛ ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░. ╨а╨╡╤А╨░╨╜╨║ ╨┐╨╛ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╨╝ ╤Н╤В╨╛╤В ╤Д╨░╨╣╨╗ ╨╜╨╡ ╨┐╨╡╤А╨╡╨╖╨░╨┐╨╕╤Б╤Л╨▓╨░╨╡╤В."""
    if ts is None:
        ts = datetime.now()
    with _safe_marker_write(marker_path, 'last_full_recalc.json') as f:
        json.dump({'last_full_recalc': ts.isoformat()}, f, ensure_ascii=False, indent=2)


# тХРтХРтХР ╨д╨╛╨╜╨╛╨▓╤Л╨╣ (async) ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В тХРтХРтХР
# ╨Я╨╛╨╗╨╜╤Л╨╣ ╨┐╤А╨╛╤Е╨╛╨┤ (150тАУ230 ╨╝╨╕╨╜) ╨╕╤Б╤В╨╛╤А╨╕╤З╨╡╤Б╨║╨╕ ╨┤╨╡╤А╨╢╨░╨╗ ╨▒╨╛╨╡╨▓╨╛╨╣ ╤Ж╨╕╨║╨╗ ╨╖╨░╨║╤А╤Л╤В╤Л╨╝: ╨▒╨░╤А╤Л ╨╜╨╡
# ╨╛╨┐╤А╨░╤И╨╕╨▓╨░╨╗╨╕╤Б╤М, ╤Б╨╕╨│╨╜╨░╨╗╤Л ╨╜╨╡ ╤А╨╛╨╢╨┤╨░╨╗╨╕╤Б╤М, ╤В╤А╨╡╨╣╨╗╨╕╨╜╨│ ╨╕ ╨░╨▓╨░╤А╨╕╨╣╨╜╤Л╨╡ ╨╖╨░╤Й╨╕╤В╤Л (daily loss,
# equity stop, margin) ╨╜╨╡ ╤Б╤А╨░╨▒╨░╤В╤Л╨▓╨░╨╗╨╕. ╨в╨╡╨┐╨╡╤А╤М ╤В╤П╨╢╤С╨╗╨░╤П ╤З╨░╤Б╤В╤М ╤Б╤З╨╕╤В╨░╨╡╤В╤Б╤П ╨▓ ╨╛╤В╨┤╨╡╨╗╤М╨╜╨╛╨╝
# ╨┐╨╛╤В╨╛╨║╨╡ (backtest_job.BacktestJob), ╤Ж╨╕╨║╨╗ ╨╢╨╕╨▓╤С╤В ╨╛╨▒╤Л╤З╨╜╨╛╨╣ ╨╢╨╕╨╖╨╜╤М╤О, ╨░ ╤А╨╡╨╖╤Г╨╗╤М╤В╨░╤В
# ╨┐╤А╨╕╨╝╨╡╨╜╤П╨╡╤В╤Б╤П ╨┐╨╛ ╨╖╨░╨▓╨╡╤А╤И╨╡╨╜╨╕╨╕ job тАФ ╨┐╨╛╨▓╤В╨╛╤А╨╜╤Л╨╝ ╨▓╤Е╨╛╨┤╨╛╨╝ ╨▓ ╨╜╨╛╤З╨╜╨╛╨╣ ╨▒╨╗╨╛╨║ (╤А╨╡╤А╨░╨╜╨║ ╨┐╨╛ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╨╝):
# job ╨┐╨╕╤И╨╡╤В ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л ╤Б╨░╨╝, ╨┐╨╛╤Н╤В╨╛╨╝╤Г ╨┐╨╡╤А╨╡╨┤╨░╨▓╨░╤В╤М ╤А╨╡╨╖╤Г╨╗╤М╤В╨░╤В╤Л ┬л╨▓ ╤А╤Г╨║╨╕┬╗ ╨╜╨╡ ╨╜╤Г╨╢╨╜╨╛.
_bg_job = None       # ╨░╨║╤В╨╕╨▓╨╜╤Л╨╣ BacktestJob (╨╛╨┤╨╜╨╛╨▓╤А╨╡╨╝╨╡╨╜╨╜╨╛ ╨╜╨╡ ╨▒╨╛╨╗╨╡╨╡ ╨╛╨┤╨╜╨╛╨│╨╛)
_bg_ready = False    # ╨╖╨░╨▓╨╡╤А╤И╤С╨╜╨╜╤Л╨╣ job ╨╢╨┤╤С╤В ╨┐╤А╨╕╨╝╨╡╨╜╨╡╨╜╨╕╤П (╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л ╤Г╨╢╨╡ ╤Б╨▓╨╡╨╢╨╕╨╡)
_bg_failed = None    # ╤В╨╡╨║╤Б╤В ╨╛╤И╨╕╨▒╨║╨╕ ╨╖╨░╨▓╨╡╤А╤И╨╕╨▓╤И╨╡╨│╨╛╤Б╤П ╤Б ╨╛╤И╨╕╨▒╨║╨╛╨╣ job (╨┤╨╗╤П ╨╗╨╛╨│╨░)
_bg_elapsed_min = 0.0


def _bg_running():
    """╨Ш╨┤╤С╤В ╨╗╨╕ ╤Д╨╛╨╜╨╛╨▓╤Л╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨┐╤А╤П╨╝╨╛ ╤Б╨╡╨╣╤З╨░╤Б."""
    return _bg_job is not None and _bg_job.running()


def _bg_start(symbols, symbol_data, strategy_params, bt_cfg):
    """╨Я╨╛╤Б╤В╨░╨▓╨╕╤В╤М ╤Д╨╛╨╜╨╛╨▓╤Л╨╣ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В. ╨Т╨╛╨╖╨▓╤А╨░╤Й╨░╨╡╤В job."""
    global _bg_job, _bg_ready, _bg_failed
    from backtest_job import BacktestJob
    _bg_ready = False
    _bg_failed = None
    _bg_job = BacktestJob(symbols, symbol_data, strategy_params, bt_cfg,
                          force_recalc=True, is_night_run=True).start()
    return _bg_job


def _bg_poll():
    """╨Ю╨┐╤А╨╛╤Б╨╕╤В╤М ╤Д╨╛╨╜╨╛╨▓╤Л╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В. True тАФ job ╨╖╨░╨▓╨╡╤А╤И╨╕╨╗╤Б╤П (╤Б╨╝╨╛╤В╤А╨╕ _bg_ready/_bg_failed).

    ╨Ч╨░╨▓╨╡╤А╤И╤С╨╜╨╜╤Л╨╣ job ┬л╤Б╤К╨╡╨┤╨░╨╡╤В╤Б╤П┬╗: ╤Б╤Б╤Л╨╗╨║╨░ ╤Б╨▒╤А╨░╤Б╤Л╨▓╨░╨╡╤В╤Б╤П, ╤З╤В╨╛╨▒╤Л ╤Б╨╗╨╡╨┤╤Г╤О╤Й╨╡╨╣ ╨╜╨╛╤З╤М╤О ╨╝╨╛╨╢╨╜╨╛
    ╨▒╤Л╨╗╨╛ ╨┐╨╛╤Б╤В╨░╨▓╨╕╤В╤М ╨╜╨╛╨▓╤Л╨╣, ╨░ ╨╕╤Б╤Е╨╛╨┤ ╤Д╨╕╨║╤Б╨╕╤А╤Г╨╡╤В╤Б╤П ╨▓ _bg_ready / _bg_failed.
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
_ingest_thread = None    # ╨╢╨╕╨▓╨╛╨╣ ╨┐╨╛╤В╨╛╨║ ╨┤╨╛╨▒╨╛╤А╨░ (None тАФ ╤Б╨▓╨╛╨▒╨╛╨┤╨╜╨╛)
_ingest_error = None     # repr ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╡╨╣ ╨╛╤И╨╕╨▒╨║╨╕ ╤Д╨╛╨╜╨╛╨▓╨╛╨│╨╛ ╨┤╨╛╨▒╨╛╤А╨░ (╨┤╨╗╤П ╨╗╨╛╨│╨░)


def _ingest_start(days=1, verbose=False):
    """╨Ч╨░╨┐╤Г╤Б╤В╨╕╤В╤М ╨┤╨╛╨▒╨╛╤А ╤Б╨┤╨╡╨╗╨╛╨║ ╨▓ trades_db ╨▓ ╨╛╤В╨┤╨╡╨╗╤М╨╜╨╛╨╝ ╨┤╨╡╨╝╨╛╨╜-╨┐╨╛╤В╨╛╨║╨╡.

    ╨Ч╨░╤З╨╡╨╝: mt5.history_deals_get + ╨╖╨░╨┐╨╕╤Б╤М ╨▓ SQLite ╨╝╨╛╨│╤Г╤В ╨╖╨░╨╜╨╕╨╝╨░╤В╤М ╨╛╤В ╤Б╨╡╨║╤Г╨╜╨┤ ╨┤╨╛
    ╨╝╨╕╨╜╤Г╤В (╤И╨╕╤А╨╛╨║╨╛╨╡ ╨╛╨║╨╜╨╛, ╨║╨╛╨╜╨║╤Г╤А╨╡╨╜╤Ж╨╕╤П ╨╖╨░ ╤Д╨░╨╣╨╗ ╨С╨Ф). ╨Т ╨│╨╗╨░╨▓╨╜╨╛╨╝ ╤Ж╨╕╨║╨╗╨╡ ╤Н╤В╨╛ ╨╖╨░╨┤╨╡╤А╨╢╨╕╨▓╨░╨╗╨╛
    ╨╛╨┐╤А╨╛╤Б ╨▒╨░╤А╨╛╨▓, ╤Б╨╕╨│╨╜╨░╨╗╤Л, ╤В╤А╨╡╨╣╨╗╨╕╨╜╨│ ╨╕ ╨░╨▓╨░╤А╨╕╨╣╨╜╤Л╨╡ ╨╖╨░╤Й╨╕╤В╤Л тАФ ╨┐╨╛╤Н╤В╨╛╨╝╤Г ╨┤╨╛╨▒╨╛╤А ╨▓╤Л╨╜╨╡╤Б╨╡╨╜
    ╨╕╨╖ ╨▒╨╗╨╛╨║╨╕╤А╤Г╤О╤Й╨╡╨│╨╛ ╤Г╤З╨░╤Б╤В╨║╨░: ╤Ж╨╕╨║╨╗ ╤Б╤В╨░╨▓╨╕╤В ╨╖╨░╨┤╨░╤З╤Г ╨╕ ╨╕╨┤╤С╤В ╨┤╨░╨╗╤М╤И╨╡.

    ╨Ю╨┤╨╜╨╛╨▓╤А╨╡╨╝╨╡╨╜╨╜╨╛ ╨╢╨╕╨▓╤С╤В ╨╜╨╡ ╨▒╨╛╨╗╨╡╨╡ ╨╛╨┤╨╜╨╛╨│╨╛ ╨┤╨╛╨▒╨╛╤А╨░. ╨Я╨╛╤В╨╛╨║-╨┤╨╡╨╝╨╛╨╜: ╤Г╨╝╨╕╤А╨░╨╡╤В ╤Б ╨┐╤А╨╛╤Ж╨╡╤Б╤Б╨╛╨╝,
    ╤В╨╛╤А╨│╨╛╨▓╨╗╤О ╨╜╨╡ ╤В╤А╨╛╨│╨░╨╡╤В. ╨Ю╤И╨╕╨▒╨║╨╕ ╨╜╨╡ ╨╗╨╡╤В╤П╤В ╨▓ ╨▓╤Л╨╖╤Л╨▓╨░╤О╤Й╨╕╨╣ ╨║╨╛╨┤, ╨░ ╨║╨╛╨┐╤П╤В╤Б╤П ╨▓
    _ingest_error (╨┐╨╡╤З╨░╤В╨░╨╡╤В╤Б╤П ╨┐╤А╨╕ ╤Б╨╗╨╡╨┤╤Г╤О╤Й╨╡╨╝ ╨╖╨░╨┐╤Г╤Б╨║╨╡ ╨┤╨╛╨▒╨╛╤А╨░).
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
        except Exception as exc:   # fail-safe: ╨С╨Ф ╨╜╨╡ ╨┤╨╛╨╗╨╢╨╜╨░ ╤А╨╛╨╜╤П╤В╤М ╨┐╨░╨╣╨┐╨╗╨░╨╣╨╜
            _ingest_error = repr(exc)

    import threading
    _ingest_thread = threading.Thread(target=_run, name='trades_db_ingest', daemon=True)
    _ingest_thread.start()
    return True


# тХРтХРтХР ╨б╤В╨░╤В╤Г╤Б ╤Б╨╡╨╝╨╡╨╣╤Б╤В╨▓ ╨▓ ╨С╨Ф (╤В╨░╨▒╨╗╨╕╤Ж╨░ family_status, journals/trades.db) тХРтХРтХР
def _record_family_status(all_results, active, run_kind=None):
    """╨б╨╜╨░╨┐╤И╨╛╤В family_status тАФ ╤Б╤В╤А╨╛╨│╨╛ ╨Я╨Ю╨б╨Ы╨Х ╤А╨╡╤А╨░╨╜╨║╨░ (╨┐╨╛╤Б╨╗╨╡ sync_active_strategies).

    ╨Ю╤В╨▓╨╡╤З╨░╨╡╤В ╨╜╨░ ╨▓╨╛╨┐╤А╨╛╤Б ┬л╨║╨░╨║╨╕╨╡ ╤Б╨╡╨╝╨╡╨╣╤Б╤В╨▓╨░ ╨┐╨╛╨╗╨╜╨╛╤Б╤В╤М╤О ╤Г╤З╨░╤Б╤В╨▓╤Г╤О╤В ╨▓ ╨╜╨╛╤З╨╜╤Л╤Е ╤А╤Н╨╜╨║╨╕╨╜╨│╨░╤Е ╨╕
    ╨│╨╛╤В╨╛╨▓╤Л ╨║ ╤В╨╛╤А╨│╨╛╨▓╨╗╨╡┬╗. ╨н╤В╨╛ ╨Я╨Х╨а╨Х╨Ч╨Р╨Я╨Ш╨б╨м ╤Б╨╛╤Б╤В╨╛╤П╨╜╨╕╤П, ╨░ ╨╜╨╡ ╨╗╨╛╨│: ╨╛╨┤╨╜╨░ ╤Б╤В╤А╨╛╨║╨░ ╨╜╨░
    (symbol, family), ╨╛╤В╨▓╨╡╤В ╨╛╨┤╨╜╨╕╨╝ SELECT ╨┐╨╛ ╨║╨╗╤О╤З╤Г. ╨Ш╤Б╤В╨╛╤А╨╕╤П ┬л╨║╨╛╨│╨┤╨░ ╨▓╨╛╤И╨╗╨╛/╨▓╤Л╤И╨╗╨╛┬╗
    ╨╢╨╕╨▓╤С╤В ╨▓ first_ready_at/last_ready_at + ╨╢╤Г╤А╨╜╨░╨╗ ╨┐╨╡╤А╨╡╤Е╨╛╨┤╨╛╨▓ family_status_log.

    run_kind тАФ ╤А╨╡╨╢╨╕╨╝ ╨┐╤А╨╛╨│╨╛╨╜╨░ (full/incremental/partial/none); ╨┐╨╛ ╤Г╨╝╨╛╨╗╤З╨░╨╜╨╕╤О
    ╨▒╨╡╤А╤С╤В╤Б╤П ╨╕╨╖ functions.LAST_RUN_KIND (╨╡╨│╨╛ ╨▓╤Л╤Б╤В╨░╨▓╨╗╤П╨╡╤В run_full_backtest).
    Fail-safe: ╨╗╤О╨▒╨░╤П ╨╛╤И╨╕╨▒╨║╨░ ╨│╨░╤Б╨╕╤В╤Б╤П, ╤Ж╨╕╨║╨╗ ╨╕ ╤В╨╛╤А╨│╨╛╨▓╨╗╤О ╨╜╨╡ ╤В╤А╨╛╨│╨░╨╡╤В.
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
    except Exception as exc:
        print(f"  [WARN] family_status: {exc!r}", flush=True)


# тХРтХРтХР ╨г╤В╨╕╨╗╨╕╤В╨░: ╨┤╨╕╨░╨│╨╜╨╛╤Б╤В╨╕╨║╨░ тАФ ╤З╤В╨╛ ╨║╨╛╨┤ ┬л╨▓╨╕╨┤╨╕╤В┬╗ ╨┐╨╛ ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╕╨╝ ╤А╨░╤Б╤З╤С╤В╨░╨╝ тХРтХРтХР
def _file_info(path):
    """(exists, mtime_str, ╨┐╨╡╤А╨▓╤Л╨╡ 400 ╤Б╨╕╨╝╨▓╨╛╨╗╨╛╨▓ ╤Б╨╛╨┤╨╡╤А╨╢╨╕╨╝╨╛╨│╨╛) тАФ ╨┤╨╗╤П ╨┤╨╕╨░╨│╨╜╨╛╤Б╤В╨╕╨║╨╕."""
    try:
        if not os.path.exists(path):
            return False, '-', '(╤Д╨░╨╣╨╗╨░ ╨╜╨╡╤В)'
        mt = datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')
        with open(path, 'r', encoding='utf-8') as f:
            txt = f.read(400)
        return True, mt, txt.replace('\n', ' ').strip()
    except (OSError, ValueError):
        return False, '-', '(╨╜╨╡ ╤З╨╕╤В╨░╨╡╤В╤Б╤П)'


def _log_recalc_chain(now, night_reset_path, marker_path, is_first_run, gap_days,
                      days_since_full, weekend_full_due, manual_full):
    """╨Ъ╤А╨░╤В╨║╨╕╨╣ ╨▓╤Л╨▓╨╛╨┤: ╨▓╨║╨╗╤О╤З╨░╨╡╨╝ ╨╗╨╕ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╕ ╨┐╨╛ ╨║╨░╨║╨╛╨╣ ╨┐╤А╨╕╤З╨╕╨╜╨╡ (╤В╤А╨╕╨│╨│╨╡╤А ╨▓ ╤Б╨║╨╛╨▒╨║╨░╤Е).
    ╨Я╨╛╨┤╤А╨╛╨▒╨╜╨░╤П ╤Ж╨╡╨┐╨╛╤З╨║╨░ (╤Д╨░╨╣╨╗╤Л/mtime/╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л) ╨┐╨╡╤З╨░╤В╨░╨╡╤В╤Б╤П ╤В╨╛╨╗╤М╨║╨╛ ╨┐╤А╨╕ FULL_RECALC_DEBUG=True."""
    if weekend_full_due:
        _trg = '╨┐╨╡╤А╨▓╤Л╨╣ ╨╖╨░╨┐╤Г╤Б╨║ тАФ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨╛╨▓ ╨╜╨╡╤В' if is_first_run else \
               f'╨╛╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е / ╨┤╨╛╨│╨╛╨╜ (╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╕╨╣ ╨Я╨Ю╨Ы╨Э╨л╨Щ {days_since_full} ╨┤╨╜. ╨╜╨░╨╖╨░╨┤, ╨┐╨╛╤А╨╛╨│ {gap_days} ╨┤╨╜.)'
        print(f"  ЁЯФБ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В: ╨Ф╨Р ({_trg})")
    else:
        _last_txt = 'тАФ'
        try:
            with open(marker_path, 'r', encoding='utf-8') as _f:
                _ts = json.load(_f).get('last_full_recalc', '')
            if _ts:
                _last_txt = datetime.fromisoformat(_ts).strftime('%d.%m.%y %H:%M')
        except (OSError, ValueError, json.JSONDecodeError):
            pass



        print(f"  ЁЯФБ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В: ╨Э╨Х╨в (╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╕╨╣ ╨▒╤Л╨╗ {_last_txt}; ╨┐╨╛╤А╨╛╨│ {gap_days} ╨┤╨╜. тАФ ╨╛╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е ╨╖╨░╨║╤А╤Л╤В╨╛)")
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
    print("  ╨Ф╨Ш╨Р╨У╨Э╨Ю╨б╨в╨Ш╨Ъ╨Р ╨а╨Р╨б╨з╨Б╨в╨Ю╨Т тАФ ╤З╤В╨╛ ╨▓╨╕╨┤╨╕╤В ╨║╨╛╨┤ ╨╜╨░ ╤Б╤В╨░╤А╤В╨╡")
    print("тХР" * 66)
    print(f"  ╨Т╤А╨╡╨╝╤П:              {now.strftime('%Y-%m-%d %H:%M:%S')} ({now.strftime('%A')}, weekday={now.weekday()})")
    print(f"  ╨а╨░╨▒╨╛╤З╨░╤П ╨┐╨░╨┐╨║╨░:      {os.getcwd()}")
    print(f"  ╨Я╨░╨┐╨║╨░ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨╛╨▓:   {ckpt_dir}")
    print(f"  ╨Р╨▓╤В╨╛-╨┐╨╛╨╗╨╜╤Л╨╣ ╨╜╨░ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е: ╨Т╨Ъ╨Ы, ╨┐╨╛╤А╨╛╨│ gap = {gap_days} ╨┤╨╜.")
    print(f"  night_reset.json:       exists={nr_e} | mtime={nr_m}")
    print(f"      тЖ│ {nr_c}")
    print(f"  last_full_recalc.json:  exists={mk_e} | mtime={mk_m}")
    print(f"      тЖ│ {mk_c}")
    print(f"  last_run.json:          exists={lr_e} | mtime={lr_m}")
    print(f"      тЖ│ {lr_c}")
    print(f"  ╨з╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л ╤Б╨╕╨╝╨▓╨╛╨╗╨╛╨▓: {len(sym_files)} ╤И╤В | ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╕╨╣ ╨╕╨╖╨╝╨╡╨╜╤С╨╜: {last_sym_mtime}")
    print("  тФАтФА ╤А╨╡╤И╨╡╨╜╨╕╨╡ тФАтФА")
    print(f"  is_first_run={is_first_run} | ╨┤╨╜╨╡╨╣ ╤Б ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╡╨│╨╛ ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю = {days_since_full} | weekend_full_due={weekend_full_due}")
    if weekend_full_due or now.weekday() >= 5:
        if weekend_full_due:
            print("  тЖТ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨Ч╨Р╨Я╨г╨б╨Ъ╨Р╨Х╨Ь (╨╛╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е / ╨┤╨╛╨│╨╛╨╜)")
        else:
            print("  тЖТ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨Э╨Х ╨╖╨░╨┐╤Г╤Б╨║╨░╨╡╨╝ тАФ ╤А╨╡╤А╨░╨╜╨║ ╨┐╨╛ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╨╝")
    else:
        print("  тЖТ ╨С╤Г╨┤╨╜╨╕╨╣ ╨┤╨╡╨╜╤М: ╤А╨╡╤А╨░╨╜╨║ ╨┐╨╛ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╨╝ (╤Б╨╡╤В╨║╤Г ╨╜╨╡ ╨┐╨╡╤А╨╡╤Б╤З╨╕╤В╤Л╨▓╨░╨╡╨╝)")
    print("тХР" * 66 + "\n")


# тХРтХРтХР ╨и╨в╨г╨а╨Т╨Р╨Ы (╨Ю╨С╨п╨Ч╨Р╨в╨Х╨Ы╨м╨Э╨л╨Щ ╤И╨░╨│ ╨┐╨░╨╣╨┐╨╗╨░╨╣╨╜╨░) тХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХРтХР
def run_steering_wheel(active_strategies, active, symbol_data, balance,
                       risk_cfg, steering_cfg, journal_dir=None, tag=''):
    """╨Я╨╡╤А╨╡╤Б╤З╤С╤В ╨║╨▓╨╛╤В ╨┐╨╛ ╨║╨░╤В╨╡╨│╨╛╤А╨╕╤П╨╝ symbol+family ╨╕ ╨┐╨╡╤А╨╡╨║╨╗╨░╨┤╨║╨░ ╨╗╨╛╤В╨╛╨▓ ╨┐╨╛ ╤А╨╡╨░╨╗╤М╨╜╤Л╨╝ ╤Б╨┤╨╡╨╗╨║╨░╨╝.

    ╨Ю╨С╨п╨Ч╨Р╨в╨Х╨Ы╨м╨Э╨л╨Щ ╤И╨░╨│: ╨▓╤Л╨╖╤Л╨▓╨░╨╡╤В╤Б╤П ╨┐╤А╨╕ ╤Б╤В╨░╤А╤В╨╡, ╤Б╤А╨░╨╖╤Г ╨┐╨╛╤Б╨╗╨╡ ╨╜╨╛╤З╨╜╨╛╨│╨╛ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ ╨╕ ╨┤╨░╨╗╨╡╨╡
    ╨║╨░╨╢╨┤╤Л╨╡ steering_cfg.interval_sec тАФ ╨╜╨╡╨╖╨░╨▓╨╕╤Б╨╕╨╝╨╛ ╨╛╤В ╤В╨╛╨│╨╛, ╨▒╤Л╨╗ ╨╗╨╕ ╨▒╤Н╨║╤В╨╡╤Б╤В.
    ╨а╨░╨╜╤М╤И╨╡ ╨▒╨╗╨╛╨║ ╨╢╨╕╨╗ ╨▓╨╜╤Г╤В╤А╨╕ ╨▓╨╡╤В╨║╨╕ ╨▒╤Н╨║╤В╨╡╤Б╤В╨░ ╨╕ ╨▓╨╜╤Г╤В╤А╨╕ `if metrics:`, ╨┐╨╛╤Н╤В╨╛╨╝╤Г ╤И╤В╤Г╤А╨▓╨░╨╗
    ╨╝╨╛╨╗╤З╨░ ╨┐╤А╨╛╨┐╤Г╤Б╨║╨░╨╗╤Б╤П, ╨╡╤Б╨╗╨╕ ╨▓ ╨╛╨║╨╜╨╡ ╨╜╨╡ ╨▒╤Л╨╗╨╛ ╤Б╨┤╨╡╨╗╨╛╨║. ╨в╨╡╨┐╨╡╤А╤М ╨╗╤О╨▒╨░╤П ╨┐╤А╨╕╤З╨╕╨╜╨░ ╨┐╤А╨╛╨┐╤Г╤Б╨║╨░
    ╨┐╨╡╤З╨░╤В╨░╨╡╤В╤Б╤П ╨▓ ╨╗╨╛╨│: ╨╜╨╡╤В ╨╝╨╡╤В╤А╨╕╨║ тЖТ ╨▒╨╡╤А╤С╨╝ ╤Б╨╛╤Е╤А╨░╨╜╤С╨╜╨╜╤Л╨╡ ╨║╨▓╨╛╤В╤Л; ╨╜╨╡╤В ╨║╨▓╨╛╤В╤Л ╤Г ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕,
    sl_money<=0, ╨▒╤О╨┤╨╢╨╡╤В<=0, ╨╛╤В╨║╤А╤Л╤В╨░╤П ╨┐╨╛╨╖╨╕╤Ж╨╕╤П тАФ ╤Б╤З╨╕╤В╨░╤О╤В╤Б╤П ╨╛╤В╨┤╨╡╨╗╤М╨╜╨╛.

    ╨Т╨╛╨╖╨▓╤А╨░╤Й╨░╨╡╤В dict ╤Б╨╛ ╤Б╤З╤С╤В╤З╨╕╨║╨░╨╝╨╕ (changed/synced/no_quota/bad_sl/no_budget/
    with_position/unchanged/categories/source). ╨Ш╤Б╨║╨╗╤О╤З╨╡╨╜╨╕╤П ╨╜╨╡ ╨┐╤А╨╛╨▒╤А╨░╤Б╤Л╨▓╨░╤О╤В╤Б╤П:
    ╨┐╨░╨╣╨┐╨╗╨░╨╣╨╜ ╨╜╨╡ ╨┤╨╛╨╗╨╢╨╡╨╜ ╨┐╨░╨┤╨░╤В╤М ╨╕╨╖-╨╖╨░ ╤И╤В╤Г╤А╨▓╨░╨╗╨░, ╨╜╨╛ ╨╛╤И╨╕╨▒╨║╨░ ╨┐╨╡╤З╨░╤В╨░╨╡╤В╤Б╤П ╨║╨░╨║ [ERROR].
    """
    journal_dir = journal_dir or JOURNAL_DIR
    st = {'changed': 0, 'synced': 0, 'no_quota': 0, 'bad_sl': 0, 'no_budget': 0,
          'killed': 0, 'tilt': {},
          'with_position': 0, 'unchanged': 0, 'categories': 0, 'source': 'none'}
    # st: ╤Б╤З╤С╤В╤З╨╕╨║╨╕ ╨┐╤А╨╛╨│╨╛╨╜╨░ (killed тАФ ╤Б╨║╨╛╨╗╤М╨║╨╛ ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╣ ╨╛╤Б╤В╨░╨╜╨╛╨▓╨╕╨╗ kill switch)
    _tag = f" {tag}" if tag else ''
    print(f"\n  [STEERING] ╨б╤В╨░╤А╤В{_tag}: {len(active_strategies or {})} ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╣, "
          f"╨╛╨║╨╜╨╛ {steering_cfg.lookback_days} ╨┤╨╜., ╨▒╨░╨╗╨░╨╜╤Б {balance:,.0f} тВ╜", flush=True)

    try:
        quotas_path = os.path.join(journal_dir, steering_cfg.quotas_file)
        prev_quotas = {}
        if os.path.exists(quotas_path):
            try:
                with open(quotas_path, 'r', encoding='utf-8') as _qf:
                    prev_quotas = json.load(_qf) or {}
            except Exception as _qe:
                print(f"  [ERROR] ╨и╤В╤Г╤А╨▓╨░╨╗: {quotas_path} ╨╜╨╡ ╤З╨╕╤В╨░╨╡╤В╤Б╤П ({_qe!r}) тАФ "
                      f"╤Б╤З╨╕╤В╨░╨╡╨╝ ╨║╨▓╨╛╤В╤Л ╤Б ╨╜╤Г╨╗╤П", flush=True)
                prev_quotas = {}

        # тФАтФА ╨Ш╤Б╤В╨╛╤З╨╜╨╕╨║: Strategy Tree (╨╛╨║╨╜╨╛ lookback_days), ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ symbol+family тФАтФА
        # ╨в╨░ ╨╢╨╡ ╨▓╤Л╨▒╨╛╤А╨║╨░ ╤Б╨┤╨╡╨╗╨╛╨║, ╤З╤В╨╛ ╨▓ ╨┤╨╡╤А╨╡╨▓╨╡/╤И╤В╤Г╤А╨▓╨░╨╗╨╡ ╨┤╤Н╤И╨▒╨╛╤А╨┤╨░: ╤З╨╕╤Б╨╗╨░ ╤Б╨╛╨▓╨┐╨░╨┤╨░╤О╤В 1-╨▓-1.
        metrics = []
        try:
            _alloc = get_dashboard_data(steering_cfg.lookback_days, manage_connection=False)
            _adeals = _alloc.get('trades_df') if _alloc else None
            metrics = compute_categories(_adeals) if _adeals is not None else []
        except Exception as _de:
            print(f"  [ERROR] ╨и╤В╤Г╤А╨▓╨░╨╗: Strategy Tree ╨╜╨╡╨┤╨╛╤Б╤В╤Г╨┐╨╡╨╜ ({_de!r}) тАФ "
                  f"╤А╨░╨▒╨╛╤В╨░╨╡╨╝ ╨╜╨░ ╤Б╨╛╤Е╤А╨░╨╜╤С╨╜╨╜╤Л╤Е ╨║╨▓╨╛╤В╨░╤Е", flush=True)

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
                    # ╨Я╨╛╨╗╨╕╤В╨╕╨║╨░ ╨┐╨╛╤В╨╡╤А╤М (kill switch): ╨┐╨╛╤А╨╛╨│ ╨▓ ╤А╤Г╨▒╨╗╤П╤Е, ╤А╤Г╨▒╨╗╤С╨▓╨░╤П ╤А╨╕╤Б╨║-╨║╨▓╨╛╤В╨░
                    'quota_rub': balance * risk_cfg.max_risk_pct,
                    'loss_decay': getattr(steering_cfg, 'loss_decay', 0.25),
                    'kill_pnl_pct': getattr(steering_cfg, 'kill_pnl_pct', 0.02),
                    'kill_pnl_rub': getattr(steering_cfg, 'kill_pnl_rub', 0.0),
                    'kill_min_trades': getattr(steering_cfg, 'kill_min_trades', 3),
                },
                # ╨Ъ╨░╤В╨╡╨│╨╛╤А╨╕╨╕ ╨░╨║╤В╨╕╨▓╨╜╨╛╨│╨╛ ╨┐╨╗╨░╨╜╨░ тАФ ╨┤╨░╨╢╨╡ ╨▒╨╡╨╖ ╤Б╨┤╨╡╨╗╨╛╨║ ╨▓ ╨╛╨║╨╜╨╡ ╨┤╨╛╨╗╨╢╨╜╤Л ╨┐╨╛╨╗╤Г╤З╨╕╤В╤М
                # ╨║╨╗╤О╤З ╨▓ ╤Д╨░╨╣╨╗╨╡ ╨║╨▓╨╛╤В, ╨╕╨╜╨░╤З╨╡ ╤И╤В╤Г╤А╨▓╨░╨╗ ╨╜╨╡ ╨╝╨╛╨╢╨╡╤В ╤В╤А╨╛╨╜╤Г╤В╤М ╨╕╤Е ╨╗╨╛╤В.
                known_ids=sorted({_cid for _cid in (record_category_id(_s)
                                                    for _s in (active_strategies or {}).values())
                                  if _cid}),
            )
            with open(quotas_path, 'w', encoding='utf-8') as _qf:
                json.dump(new_quotas, _qf, ensure_ascii=False, indent=2)

            # тФАтФА ╨Я╤А╨╕╨╜╤В: Strategy Tree тЖТ ╨┐╨╡╤А╨╡╨║╨╗╨░╨┤╨║╨░ ╨╛╨▒╤К╤С╨╝╨░ тФАтФА
            print(f"\n  [WHEEL] ╨Я╨╡╤А╨╡╤Б╤З╤С╤В ╨║╨▓╨╛╤В (score_mode={steering_cfg.score_mode}) "
                  f"(╨╛╨║╨╜╨╛ {steering_cfg.lookback_days} ╨┤╨╜.).", flush=True)
            for _line in format_allocation_report(
                    metrics, prev_quotas, new_quotas,
                    steering_cfg.lookback_days,
                    min_trades=steering_cfg.min_trades,
                    score_mode=steering_cfg.score_mode):
                print(_line, flush=True)
            st['source'] = 'tree'
        else:
            print(f"  [WHEEL] ╨б╨▓╨╡╨╢╨╕╤Е ╤Б╨┤╨╡╨╗╨╛╨║ ╨╖╨░ {steering_cfg.lookback_days} ╨┤╨╜. ╨╜╨╡╤В тАФ "
                  f"╨┐╨╡╤А╨╡╨║╨╗╨░╨┤╨║╨░ ╨┐╨╛ ╤Б╨╛╤Е╤А╨░╨╜╤С╨╜╨╜╤Л╨╝ ╨║╨▓╨╛╤В╨░╨╝: {len(new_quotas)} ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╣ "
                  f"({steering_cfg.quotas_file})", flush=True)
            st['source'] = 'saved'

        st['categories'] = len(new_quotas)
        if not new_quotas:
            print("  [ERROR] ╨и╤В╤Г╤А╨▓╨░╨╗: ╨║╨▓╨╛╤В ╨╜╨╡╤В ╨▓╨╛╨╛╨▒╤Й╨╡ (╨╜╨╡╤В ╨╜╨╕ ╨╝╨╡╤В╤А╨╕╨║ Strategy Tree, ╨╜╨╕ ╤Д╨░╨╣╨╗╨░ "
                  f"{steering_cfg.quotas_file}) тАФ ╨╗╨╛╤В╤Л ╨╜╨╡ ╤В╤А╨╛╨╜╤Г╤В╤Л", flush=True)
            return st

        # тФАтФА ╨Я╨╡╤А╨╡╨║╨╗╨░╨┤╨║╨░ ╨╗╨╛╤В╨╛╨▓: ╨Р╨С╨б╨Ю╨Ы╨о╨в╨Э╨л╨Щ ╤Ж╨╡╨╗╨╡╨▓╨╛╨╣ ╨╗╨╛╤В тФАтФА
        #     lot_i = (budget ├Ч q_i / ╬гq_covered) ├Ч (score_i / ╬гscore_╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕) / sl_money_i
        # budget тАФ ╤Б╨▓╨╛╨▒╨╛╨┤╨╜╨░╤П ╤З╨░╤Б╤В╤М ╤А╨╕╤Б╨║-╨║╨▓╨╛╤В╤Л (╨╖╨░ ╨▓╤Л╤З╨╡╤В╨╛╨╝ ╤А╨╕╤Б╨║╨░ ╨╛╤В╨║╤А╤Л╤В╤Л╤Е ╨┐╨╛╨╖╨╕╤Ж╨╕╨╣),
        # ╨┐╨╛╤Н╤В╨╛╨╝╤Г ╬г(lot├Чsl_money) тЙд quota ╨┐╨╛ ╨┐╨╛╤Б╤В╤А╨╛╨╡╨╜╨╕╤О.
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
        # ╨С╤О╨┤╨╢╨╡╤В ╨┤╨╡╨╗╨╕╨╝ ╨╜╨░ ╨Т╨б╨Х ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ ╤Б ╨╜╨╡╨╜╤Г╨╗╨╡╨▓╨╛╨╣ ╨║╨▓╨╛╤В╨╛╨╣, ╨░ ╨╜╨╡ ╤В╨╛╨╗╤М╨║╨╛ ╨╜╨░
        # ╤Б╨▓╨╛╨▒╨╛╨┤╨╜╤Л╨╡: ╨╕╨╜╨░╤З╨╡ ╤Б╨▓╨╛╨▒╨╛╨┤╨╜╨░╤П ╤Б╤В╤А╨░╤В╨╡╨│╨╕╤П ╤Б ╨║╨▓╨╛╤В╨╛╨╣-╨┐╨╛╨╗╨╛╨╝ (1.04%) ╨╖╨░╨▒╨╕╤А╨░╨╗╨░
        # ╨▓╨╡╤Б╤М ╨╜╨╡╨╖╨░╨╜╤П╤В╤Л╨╣ ╨▒╤О╨┤╨╢╨╡╤В ╨╕ ╨┐╨╛╨╗╤Г╤З╨░╨╗╨░ ╤А╨╕╤Б╨║ ╨▓ 1.8├Ч ╨╛╤В ╨╜╨╛╨╝╨╕╨╜╨░╨╗╨░
        # (17.10: EURUSDrf_pin_bar тАФ 4,003 тВ╜ ╨▓╨╝╨╡╤Б╤В╨╛ 2,214 тВ╜).
        # Budget is split only over categories that really receive lots (the plan).
        # Old formula summed ALL quotas from the file (~0.675) while plan categories
        # hold ~0.16, so only ~24% of the budget reached lots (quota used ~33%).
        _q_covered = sum(v for sid, v in new_quotas.items() if v > 0 and sid in _free_sids)
        if _q_covered <= 0:
            _q_covered = sum(v for v in new_quotas.values() if v > 0)
        _budget = max(0.0, risk_quota - _used_risk)
        print(f"  [STEERING] ╨б╨▓╨╛╨▒╨╛╨┤╨╜╤Л╤Е {len(_free_keys)} | ╨▓ ╨┐╨╛╨╖╨╕╤Ж╨╕╤П╤Е {st['with_position']} | "
              f"╤А╨╕╤Б╨║ ╨┐╨╛╨╖╨╕╤Ж╨╕╨╣ {_used_risk:,.0f} тВ╜ | ╨▒╤О╨┤╨╢╨╡╤В {_budget:,.0f} тВ╜ ╨╕╨╖ "
              f"{risk_quota:,.0f} тВ╜ | ╬гq ╨▓╤Б╨╡╤Е ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╣ {_q_covered:.3f}", flush=True)
        if _budget <= 0:
            print("  [ERROR] ╨и╤В╤Г╤А╨▓╨░╨╗: ╤Б╨▓╨╛╨▒╨╛╨┤╨╜╨╛╨│╨╛ ╨▒╤О╨┤╨╢╨╡╤В╨░ ╨╜╨╡╤В (╨║╨▓╨╛╤В╨░ ╨╖╨░╨╜╤П╤В╨░ ╨╛╤В╨║╤А╤Л╤В╤Л╨╝╨╕ "
                  "╨┐╨╛╨╖╨╕╤Ж╨╕╤П╨╝╨╕) тАФ ╨╗╨╛╤В╤Л ╨╜╨╡ ╨┐╨╡╤А╨╡╨╗╨╛╨╢╨╡╨╜╤Л", flush=True)
            st['no_budget'] = len(_free_keys)
            return st

        for key, s in active_strategies.items():
            if s['position'] is not None:
                continue
            sid = record_category_id(s)
            # ╨б╨╜╤П╤В╤М ╤В╨╕╨╗╤М╤В ╨┐╤А╨╛╤И╨╗╨╛╨│╨╛ ╤Ж╨╕╨║╨╗╨░: ╤Б╤З╨╕╤В╨░╨╡╨╝ ╨╕ ╤Б╤А╨░╨▓╨╜╨╕╨▓╨░╨╡╨╝ ╤Б ╨Ы╨Ю╨в╨Ю╨Ь-╨С╨Р╨Ч╨Ш╨б╨Ю╨Ь,
            # ╨╕╨╜╨░╤З╨╡ ╤И╤В╤Г╤А╨▓╨░╨╗ ╨║╨░╨╢╨┤╤Л╨╣ ╤З╨░╤Б ┬л╨╜╨░╤Е╨╛╨┤╨╕╤В┬╗ ╨╕╨╖╨╝╨╡╨╜╨╡╨╜╨╕╨╡ ╤В╨░╨╝, ╨│╨┤╨╡ ╨╗╨╛╤В ╨┐╤А╨╛╤Б╤В╨╛
            # ╨╜╨╡╤Б╤С╤В ╨╜╨░╨┤╨▒╨░╨▓╨║╤Г ┬▒20% (╤В╨╕╨╗╤М╤В ╨┐╤А╨╕╨╝╨╡╨╜╨╕╤В╤Б╤П ╨╖╨░╨╜╨╛╨▓╨╛ ╨▓ ╨║╨╛╨╜╤Ж╨╡ ╤Н╤В╨╛╨╣ ╤Д╤Г╨╜╨║╤Ж╨╕╨╕).
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
                print(f"  [WARN] ╨и╤В╤Г╤А╨▓╨░╨╗: {key} тАФ ╨╜╨╡╤В ╨║╨▓╨╛╤В╤Л ╨┤╨╗╤П ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ {sid!r}, "
                      f"╨╗╨╛╤В ╨╜╨╡ ╤В╤А╨╛╨╜╤Г╤В", flush=True)
                continue
            _m = _slm.get(key, 0.0)
            if q_new <= 0:
                # Kill switch: ╨║╨░╤В╨╡╨│╨╛╤А╨╕╤П ╤Г╨▒╤Л╤В╨╛╤З╨╜╨░ (╨║╨▓╨╛╤В╨░ 0) тЖТ ╨╜╨╛╨▓╤Л╨╡ ╨▓╤Е╨╛╨┤╤Л ╨╖╨░╨┐╤А╨╡╤Й╨╡╨╜╤Л.
                if s.get('enabled', True) or float(s.get('lot') or 0) > 0:
                    print(f"  [WHEEL] KILL {key}: q=0 тЖТ ╤В╨╛╤А╨│╨╛╨▓╨╗╤П ╨╛╤Б╤В╨░╨╜╨╛╨▓╨╗╨╡╨╜╨░ "
                          f"(╨║╨░╤В╨╡╨│╨╛╤А╨╕╤П {sid}, ╨╗╨╛╤В {s['lot']:.3f} тЖТ 0)", flush=True)
                s['lot'] = 0.0
                s['enabled'] = False
                s['disabled_reason'] = f'steering: ╨║╨▓╨╛╤В╨░ ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ {sid} = 0 (╨╢╨╕╨▓╨╛╨╣ ╤Г╨▒╤Л╤В╨╛╨║)'
                st['killed'] += 1
                continue
            if s.get('enabled', True) is False:
                print(f"  [WHEEL] ╨▓╨╛╨╖╨▓╤А╨░╤В ╨▓ ╤А╨░╨▒╨╛╤В╤Г: {key} (╨║╨░╤В╨╡╨│╨╛╤А╨╕╤П {sid} ╤Б╨╜╨╛╨▓╨░ ╨▓ ╨┐╨╗╤О╤Б╨╡)", flush=True)
                s['enabled'] = True
                s.pop('disabled_reason', None)
            _m = _slm.get(key, 0.0)
            if _m <= 0 or _q_covered <= 0:
                st['bad_sl'] += 1
                print(f"  [WARN] ╨и╤В╤Г╤А╨▓╨░╨╗: {key} тАФ sl_money={_m:,.2f} ╨╕╨╗╨╕ ╬гq={_q_covered:.3f}, "
                      f"╨╗╨╛╤В ╨╜╨╡ ╤В╤А╨╛╨╜╤Г╤В", flush=True)
                continue
            # ╨Ф╨╛╨╗╤П ╨▓╨╜╤Г╤В╤А╨╕ ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ тАФ ╨┐╨╛ score ╨▒╤Н╨║╤В╨╡╤Б╤В╨░ (╨║╨░╨║ ╨▓ tree_weighted_lots);
            # ╨┐╨╛╤А╨╛╨▓╨╜╤Г тАФ ╤В╨╛╨╗╤М╨║╨╛ ╨╡╤Б╨╗╨╕ ╬гscore ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ = 0.
            _sc = max(float(s.get('score') or 0.0), 0.0)
            _scat = _score_sum_cat.get(sid, 0.0)
            _share = (_sc / _scat) if _scat > 0 else (1.0 / max(1, _n_in_cat.get(sid, 1)))
            new_lot = _budget * (q_new / _q_covered) * _share / _m
            _info = symbol_data.get(s['symbol'], {}).get('info')
            _vol = _normalize_volume(new_lot, _info)
            new_lot = max(_vol if _vol is not None else risk_cfg.min_lot, risk_cfg.min_lot)
            if abs(new_lot - s['lot']) > 1e-9:
                print(f"  [STEERING] {key}: lot {s['lot']:.3f} -> {new_lot:.3f} "
                      f"(q {q_new:.3f}, score {_sc:.2f}/{_scat:.2f}, ╤А╨╕╤Б╨║ "
                      f"{s['lot'] * _m:,.0f} -> {new_lot * _m:,.0f} тВ╜)")
                s['lot'] = new_lot
                st['changed'] += 1
            else:
                st['unchanged'] += 1

        # тФАтФА ╨Я╤А╨╡╨╝╨╕╤П/╨┤╨╕╤Б╨║╨╛╨╜╤В ╨┐╨╛ ╤В╨░╨║╤В╨╕╨║╨╡ ╨▓╤Е╨╛╨┤╨░ (┬▒20% ╨║ ╨╛╨▒╤К╤С╨╝╤Г): ╨б╨Р╨Ь╨л╨Щ ╨Ъ╨Ю╨Э╨Х╨ж ╤А╨╡╤А╨░╨╜╨║╨░ тФАтФА
        # ╨Ю╨▒╤К╤С╨╝ ╤Г╨╢╨╡ ╨┐╨╡╤А╨╡╨╗╨╛╨╢╨╡╨╜ ╤И╤В╤Г╤А╨▓╨░╨╗╨╛╨╝ тАФ ╨╖╨┤╨╡╤Б╤М ╨╛╨╜ ╤В╨╛╨╗╤М╨║╨╛ ╨╝╨░╤Б╤И╤В╨░╨▒╨╕╤А╤Г╨╡╤В╤Б╤П ╨┐╨╛ ╨╗╤Г╤З╤И╨╡╨╣/
        # ╤Е╤Г╨┤╤И╨╡╨╣ ╤Б╨▓╤П╨╖╨║╨╡ ┬л╨┐╨░╤А╨░ + ╨┤╨╡╨╜╤М ╨▓╤Л╤Е╨╛╨┤╨░┬╗ ╨╖╨░ ╨╛╨║╨╜╨╛ ╨┤╨╛ 90 ╨┤╨╜╨╡╨╣ (tactic_tilt.py).
        # ╨Ш╨┤╨╡╨╝╨┐╨╛╤В╨╡╨╜╤В╨╜╨╛: ╨┐╨╛╨▓╤В╨╛╤А╨╜╤Л╨╣ ╨▓╤Л╨╖╨╛╨▓ ╤Б ╤В╨╡╨╝ ╨╢╨╡ ╨╝╨╜╨╛╨╢╨╕╤В╨╡╨╗╨╡╨╝ ╨▓╤В╨╛╤А╨╛╨╣ ╤А╨░╨╖ ┬▒20% ╨╜╨╡
        # ╨╜╨░╤З╨╕╤Б╨╗╤П╨╡╤В (╨╝╨░╤А╨║╨╡╤А╤Л tilt_base/tilt_mult), ╨░ ╨╗╨╛╤В ╨╛╤В ╤И╤В╤Г╤А╨▓╨░╨╗╨░ тАФ ╨╜╨╛╨▓╤Л╨╣ ╨▒╨░╨╖╨╕╤Б.
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
        # ╨и╤В╤Г╤А╨▓╨░╨╗ ╨┐╤А╨░╨▓╨╕╤В active_strategies тАФ ╤Н╤В╨╛ ╨╕ ╨╡╤Б╤В╤М ╨▒╨╛╨╣. ╨Я╨╡╤А╨╡╨╜╨╛╤Б╨╕╨╝ ╨╕╤В╨╛╨│ ╨╛╨▒╤А╨░╤В╨╜╨╛
        # ╨▓ ╨┐╨╗╨░╨╜ (active), ╤З╤В╨╛╨▒╤Л active_state.json/╨┤╤Н╤И╨▒╨╛╤А╨┤ ╨┐╨╛╨║╨░╨╖╤Л╨▓╨░╨╗╨╕ ╤А╨╡╨░╨╗╤М╨╜╤Г╤О
        # ╨┐╨╡╤А╨╡╨║╨╗╨░╨┤╨║╤Г, ╨░ ╨╜╨╡ ╨┤╨╛╤В╤О╨╜╨╡╨╜╨╜╤Л╨╣ tree-weighting ╨╗╨╛╤В. ╨Я╨╛╤Б╨╗╨╡ ╤Н╤В╨╛╨│╨╛ active == active_strategies.
        _lot_by_key = {_k: _v.get('lot') for _k, _v in active_strategies.items()}
        for _r in (active or []):
            _rk = strategy_key(_r['symbol'], _r['param_key'],
                               _r.get('type', 'stoch'),
                               _r.get('parabolic_max'))
            _nl = _lot_by_key.get(_rk)
            if _nl is not None and abs(float(_nl) - float(_r.get('lot') or 0)) > 1e-9:
                _r['lot'] = _nl
                st['synced'] += 1

        print(f"  [STEERING] ╨Ш╤В╨╛╨│: ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╣ {st['categories']} (╨╕╤Б╤В╨╛╤З╨╜╨╕╨║: {st['source']}), "
              f"╨┐╨╡╤А╨╡╨╗╨╛╨╢╨╡╨╜╨╛ {st['changed']}, ╨▒╨╡╨╖ ╨╕╨╖╨╝╨╡╨╜╨╡╨╜╨╕╨╣ {st['unchanged']}, "
              f"╤Б╨╕╨╜╤Е╤А╨╛╨╜╨╕╨╖╨╕╤А╨╛╨▓╨░╨╜╨╛ ╨▓ ╨┐╨╗╨░╨╜ {st['synced']} | ╨┐╤А╨╛╨┐╤Г╤Б╨║╨╕: ╨▓ ╨┐╨╛╨╖╨╕╤Ж╨╕╨╕ "
              f"{st['with_position']}, ╨╜╨╡╤В ╨║╨▓╨╛╤В╤Л {st['no_quota']}, sl_money/╬гq "
              f"{st['bad_sl']}, ╨▒╤О╨┤╨╢╨╡╤В {st['no_budget']}", flush=True)
        if st['killed']:
            print(f"  [STEERING] Kill switch: {st['killed']} ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╣ ╨╛╤Б╤В╨░╨╜╨╛╨▓╨╗╨╡╨╜╨╛ "
                  f"(╨║╨▓╨╛╤В╨░ ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ = 0) тАФ ╨╜╨╛╨▓╤Л╨╡ ╨▓╤Е╨╛╨┤╤Л ╨┐╨╛ ╨╜╨╕╨╝ ╨╖╨░╨┐╤А╨╡╤Й╨╡╨╜╤Л", flush=True)
        return st

    except Exception as se:
        print(f"  [ERROR] ╨и╤В╤Г╤А╨▓╨░╨╗: {se!r} тАФ ╨║╨▓╨╛╤В╤Л/╨╗╨╛╤В╤Л ╨╜╨╡ ╨╕╨╖╨╝╨╡╨╜╨╡╨╜╤Л", flush=True)
        return st


if __name__ == '__main__':
    start_time = datetime.now()
    print(f"ЁЯЪА ╨Ч╨Р╨Я╨г╨б╨Ъ ╨б╨Ш╨б╨в╨Х╨Ь╨л: {start_time.strftime('%H:%M:%S')}")

    # тХРтХРтХР ╨Ъ╨Ю╨Э╨д╨Ш╨У╨г╨а╨Р╨ж╨Ш╨п (╨╡╨┤╨╕╨╜╤Л╨╣ ╨╕╤Б╤В╨╛╤З╨╜╨╕╨║ тАФ config.py) тХРтХРтХР
    from config import build_default_configs
    app = build_default_configs()
    strategy_params = app.strategy_params
    bt_cfg = app.backtest_config
    risk_cfg = app.risk_params
    trail_cfg = app.trail_params
    steering_cfg = app.steering_params
    trail_mgr = TrailManager(trail_cfg)
    print(f"[TRAIL] {'╨Т╨Ъ╨Ы╨о╨з╨Б╨Э' if trail_cfg.enabled else '╨Т╨л╨Ъ╨Ы╨о╨з╨Х╨Э'} | "
          f"ATR(D1,{trail_cfg.atr_period}) x {trail_cfg.atr_multiplier} | "
          f"╨╕╨╜╤В╨╡╤А╨▓╨░╨╗ {trail_cfg.check_interval_sec}╤Б | ╨╝╨╕╨╜.╤Б╨┤╨▓╨╕╨│ {trail_cfg.min_move_points} ╨┐╤В")

    # тХРтХРтХР ╨Т╨л╨з╨Ш╨б╨Ы╨Ш╨в╨Х╨Ы╨м╨Э╨л╨Щ ╨С╨о╨Ф╨Ц╨Х╨в тХРтХРтХР
    def _combo(*args):
        result = 1
        for a in args:
            result *= a
        return result

    sp = strategy_params
    # ╨Х╨┤╨╕╨╜╤Л╨╣ ╤Б╤З╤С╤В ╨║╨╛╨╝╨▒╨╕╨╜╨░╤Ж╨╕╨╣ ╨╜╨░ 1 ╤Б╨╕╨╝╨▓╨╛╨╗ (╨╗╨╡╨│╨░╤Б╨╕ + ╤А╨╡╨╡╤Б╤В╤А) тАФ ╨╕╤Б╤В╨╛╤З╨╜╨╕╨║: functions.strategy_combos_per_symbol.
    # ╨а╨░╨╜╤М╤И╨╡ ╨╖╨┤╨╡╤Б╤М ╨▒╤Л╨╗ ╤Б╨▓╨╛╨╣ ╨╗╨╕╤В╨╡╤А╨░╨╗ (9018) ╨▒╨╡╨╖ 10 ╤Б╨╡╨╝╨╡╨╣╤Б╤В╨▓ ╨╕ ╨▒╨╡╨╖ ╨▒╨░╤В╤З╨░ ╤А╨╡╨╡╤Б╤В╤А╨░ тЖТ ╤А╨░╤Б╤Е╨╛╨┤╨╕╨╗╤Б╤П ╤Б ╨▒╤Н╨║╤В╨╡╤Б╤В╨╛╨╝.
    from functions import strategy_combos_per_symbol, STRATEGY_COMBO_LABELS
    integration_budgets_dict = {
        STRATEGY_COMBO_LABELS.get(k, k): v
        for k, v in strategy_combos_per_symbol(sp).items()
    }
    if False:  # legacy-╨╗╨╕╤В╨╡╤А╨░╨╗ ╨╜╨╕╨╢╨╡ (╨╜╨╡ ╨╕╤Б╨┐╨╛╨╗╤М╨╖╤Г╨╡╤В╤Б╤П); ╨╝╨╛╨╢╨╜╨╛ ╤Г╨┤╨░╨╗╨╕╤В╤М ╨▓╤А╤Г╤З╨╜╤Г╤О
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

    print("╨С╨╛╨╡╨▓╨╛╨╣ ╤А╨╡╨╢╨╕╨╝: ╨▓╤Б╨╡ ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╕, ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╨╡╤А╨╡╨▒╨╛╤А")

    # тХРтХРтХР ╨Я╨Ю╨Ф╨Ъ╨Ы╨о╨з╨Х╨Э╨Ш╨Х тХРтХРтХР
    terminal_on('demo')
    os.makedirs(JOURNAL_DIR, exist_ok=True)

    # тХРтХРтХР ╨Ч╨Р╨У╨а╨г╨Ч╨Ъ╨Р ╨Ш╨б╨в╨Ю╨а╨Ш╨Ш тХРтХРтХР
    print("╨Ч╨░╨│╤А╤Г╨╖╨║╨░ ╨╕╤Б╤В╨╛╤А╨╕╨╕...")

    loaded_symbols = []
    failed_symbols = []

    for sym in bt_cfg.symbols:
        h1 = load_h1(sym)
        if h1 is None or len(h1) < 30:
            failed_symbols.append(sym)
            continue

        # symbol_select ╨╜╤Г╨╢╨╡╨╜ ╤В╨╛╨╗╤М╨║╨╛ ╨╡╤Б╨╗╨╕ ╨┤╨░╨╗╤М╤И╨╡ ╨▒╤Г╨┤╨╡╤В ╤А╨░╨▒╨╛╤В╨░ ╤З╨╡╤А╨╡╨╖ MT5 API
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)

        if info is None:
            print(f"  тЪа {sym}: symbol_info ╨▓╨╡╤А╨╜╤Г╨╗ None тАФ ╨▒╤Н╨║╤В╨╡╤Б╤В/live ╨┐╨╛ ╤Б╨╕╨╝╨▓╨╛╨╗╤Г ╨┐╤А╨╛╨┐╤Г╤Й╨╡╨╜", flush=True)
            failed_symbols.append(sym)
            continue

        symbol_data[sym] = {
            'df_h1': h1,
            'current_hour': (h1.index[-1] + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0),
            'forming_bar': None,
            'info': info,
        }
        loaded_symbols.append(sym)

    # ╨Ш╨в╨Ю╨У╨Ю╨Т╨Р╨п ╨б╨Т╨Ю╨Ф╨Ъ╨Р (╨▓╨╝╨╡╤Б╤В╨╛ ╨║╤Г╤З╨╕ ╨╛╨┤╨╕╨╜╨░╨║╨╛╨▓╤Л╤Е ╤Б╤В╤А╨╛╨║)
    if loaded_symbols:
        print(f"тЬЕ ╨Ч╨░╨│╤А╤Г╨╢╨╡╨╜╨╛: {len(loaded_symbols)} ╤Б╨╕╨╝╨▓╨╛╨╗╨╛╨▓ ({', '.join(loaded_symbols)})")
    else:
        print("тЭМ ╨Э╨╡╤В ╨╖╨░╨│╤А╤Г╨╢╨╡╨╜╨╜╤Л╤Е ╤Б╨╕╨╝╨▓╨╛╨╗╨╛╨▓ тАФ ╨▒╤Н╨║╤В╨╡╤Б╤В ╨╜╨╡ ╨╖╨░╨┐╤Г╤Б╤В╨╕╤В╤Б╤П")

    if failed_symbols:
        print(f"тЪая╕П ╨Я╤А╨╛╨┐╤Г╤Й╨╡╨╜╨╛: {len(failed_symbols)} ╤Б╨╕╨╝╨▓╨╛╨╗╨╛╨▓ ╨╕╨╖-╨╖╨░ ╨╛╤В╤Б╤Г╤В╤Б╤В╨▓╨╕╤П ╨┤╨░╨╜╨╜╤Л╤Е ╨╕╨╗╨╕ ╨╛╤И╨╕╨▒╨╛╨║:")
        for sym in failed_symbols:
            print(f"   тАв {sym}")

    # тХРтХРтХР ╨Ц╨г╨а╨Э╨Р╨Ы тХРтХРтХР
    journal_df = load_journal(JOURNAL_FILE, COLUMNS)

    # тХРтХРтХР ╨Р╨Ъ╨в╨Ш╨Т╨Э╨л╨Х ╨б╨в╨а╨Р╨в╨Х╨У╨Ш╨Ш тХРтХРтХР
    active_strategies = {}

    # тХРтХРтХР ╨У╨Х╨Э╨Х╨а╨Р╨ж╨Ш╨п ╨Я╨а╨Ю╨Я╨г╨й╨Х╨Э╨Э╨л╨е ╨Ю╨в╨з╨Б╨в╨Ю╨Т тХРтХРтХР
    print("\n╨Я╤А╨╛╨▓╨╡╤А╨║╨░ ╨┐╤А╨╛╨┐╤Г╤Й╨╡╨╜╨╜╤Л╤Е daily ╨╛╤В╤З╤С╤В╨╛╨▓...")
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
                        print("  тЪая╕П  ╨а╨╡╨╡╤Б╤В╤А: ╨╜╨╡╨▓╨╡╤А╨╜╤Л╨╣ ╤Д╨╛╤А╨╝╨░╤В activated_at тАФ ╨╛╤В╤З╤С╤В╤Л ╨╖╨░ ╨┐╤А╨╛╤И╨╗╤Л╨╡ ╨┤╨╜╨╕ ╨┐╤А╨╛╨┐╤Г╤Й╨╡╨╜╤Л", flush=True)
                        first_date = date.today()
                    yesterday = date.today() - timedelta(days=1)
                    if first_date <= yesterday:
                        generate_missing_reports(first_date, yesterday)
    else:
        print("  тЪая╕П  ╨а╨╡╨╡╤Б╤В╤А ╨╜╨╡ ╨╜╨░╨╣╨┤╨╡╨╜ тАФ ╨╛╤В╤З╤С╤В╤Л ╨▒╤Г╨┤╤Г╤В ╨│╨╡╨╜╨╡╤А╨╕╤А╨╛╨▓╨░╤В╤М╤Б╤П ╤Б ╨┐╨╡╤А╨▓╨╛╨│╨╛ ╨┤╨╜╤П")

    # тХРтХРтХР ╨Я╨Х╨а╨Т╨л╨Щ ╨а╨Р╨б╨з╨Б╨в тХРтХРтХР
    print("\n╨С╤Н╨║╤В╨╡╤Б╤В (╨┐╨╡╤А╨▓╤Л╨╣ ╤А╨░╤Б╤З╤С╤В)...")

    FORCE_RECALC = bt_cfg.force_recalc
    night_reset_path = os.path.join(_checkpoint_dir(), 'night_reset.json')
    full_recalc_marker_path = os.path.join(_checkpoint_dir(), 'last_full_recalc.json')
    # ╨Ф╨╕╨░╨│╨╜╨╛╤Б╤В╨╕╨║╨░: ╨║╤Г╨┤╨░ ╨╕╨╝╨╡╨╜╨╜╨╛ ╨┐╨╕╤И╤Г╤В╤Б╤П ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л. ╨Ь╨╛╨╗╤З╨░╨╗╨╕╨▓╤Л╨╣ ┬л╨┐╤А╨╛╨┐╤Г╤Б╨║┬╗ ╨║╨░╤В╨░╨╗╨╛╨│╨░ ╨▓
    # ╤Б╨╕╨╜╨║╨╡ ╤В╤А╨╕ ╨┤╨╜╤П ╤Б╨║╤А╤Л╨▓╨░╨╗, ╤З╤В╨╛ ╨┐╨░╨┐╨║╨╕ ╨╜╨╡╤В ╨▓╨╛╨▓╤Б╨╡ тАФ ╨┐╤Г╤В╤М ╨┤╨╛╨╗╨╢╨╡╨╜ ╨▒╤Л╤В╤М ╨▓╨╕╨┤╨╡╨╜ ╨▓ ╨╗╨╛╨│╨╡.
    print(f"  ЁЯУБ ╨з╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л: {_checkpoint_dir()}", flush=True)
    is_first_run = not os.path.exists(night_reset_path)
    manual_full = bool(bt_cfg.full_recalc_mode)   # ╤А╤Г╤З╨╜╨╛╨╣ ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨┐╤А╨╕ ╨╖╨░╨┐╤Г╤Б╨║╨╡
    
    # тХРтХРтХР ╨Р╨Т╨в╨Ю╨Ь╨Р╨в╨Ш╨з╨Х╨б╨Ъ╨Ш╨Щ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨Я╨Х╨а╨Х╨б╨з╨Б╨в ╨Э╨Р ╨Т╨л╨е╨Ю╨Ф╨Э╨л╨е (╨б╨▒/╨Т╤Б) тХРтХРтХР
    now = datetime.now()
    weekend_full_due = False
    days_since_full = None   # ╨┤╨╗╤П ╨┤╨╕╨░╨│╨╜╨╛╤Б╤В╨╕╨║╨╕: ╤Б╨║╨╛╨╗╤М╨║╨╛ ╨┤╨╜╨╡╨╣ ╤Б ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╡╨│╨╛ ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░
    _bg_started = False      # True = ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╤А╨╛╤Е╨╛╨┤ ╨┐╨╛╤Б╤В╨░╨▓╨╗╨╡╨╜ ╤Д╨╛╨╜╨╛╨▓╤Л╨╝ job (async-╨▓╨╡╤В╨║╨░ ╨╜╨╕╨╢╨╡)
    if bt_cfg.auto_weekend_recalc or bt_cfg.full_recalc_daily:  # ╨╛╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е + ╨┤╨╛╨│╨╛╨╜ ╨▓ ╨▒╤Г╨┤╨╜╨╕, ╨╡╤Б╨╗╨╕ ╤Г╨╕╨║-╤Н╨╜╨┤ ╨┐╤А╨╛╨┐╤Г╤Й╨╡╨╜
        # ╨Ю╨┤╨╕╨╜ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╜╨░ ╨╛╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е (╨б╨▒тАУ╨Т╤Б). ╨Х╤Б╨╗╨╕ ╨╛╨║╨╜╨╛ ╨┐╤А╨╛╨┐╤Г╤Й╨╡╨╜╨╛ тАФ ╨┤╨╛╨│╨╛╨╜ ╨▓ ╨▒╤Г╨┤╨╜╨╕ (╤Б╨╝. _full_recalc_due).
        # ╨Ф╨░╤В╨░ ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╡╨│╨╛ ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ ╨▒╨╡╤А╤С╤В╤Б╤П ╨╕╨╖ last_full_recalc.json
        # (night_reset.json ╨╜╨╡ ╨│╨╛╨┤╨╕╤В╤Б╤П тАФ ╨╡╨│╨╛ ╨┐╨╡╤А╨╡╨╖╨░╨┐╨╕╤Б╤Л╨▓╨░╤О╤В ╨▓ ╤В╨╛╨╝ ╤З╨╕╤Б╨╗╨╡ ╨▒╤Г╨┤╨╜╨╕╨╡ ╤А╨╡╤А╨░╨╜╨║╨╕).
        if not is_first_run:
            try:
                with open(full_recalc_marker_path, 'r', encoding='utf-8') as _f:
                    _reset_ts = json.load(_f).get('last_full_recalc', '')
                if _reset_ts:
                    _last_full_date = datetime.fromisoformat(_reset_ts).date()
                    days_since_full = (now.date() - _last_full_date).days
                    # ╨Я╤А╨░╨▓╨╕╨╗╨╛: ╨╛╨┤╨╕╨╜ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨╜╨░ ╨╛╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е (╨б╨▒тАУ╨Т╤Б) + ╨┤╨╛╨│╨╛╨╜ ╨▓ ╨▒╤Г╨┤╨╜╨╕, ╨╡╤Б╨╗╨╕ ╨╛╨║╨╜╨╛ ╨┐╤А╨╛╨┐╤Г╤Й╨╡╨╜╨╛.
                    # ╨Я╨╛╤А╨░ ╨╗╨╕ ╨Я╨Ю╨Ы╨Э╨л╨Щ: ╨╛╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е (╨б╨▒тАУ╨Т╤Б) ╨╗╨╕╨▒╨╛ ╨┤╨╛╨│╨╛╨╜, ╨╡╤Б╨╗╨╕ ╨╛╨║╨╜╨╛ ╨┐╤А╨╛╨┐╤Г╤Й╨╡╨╜╨╛
                    weekend_full_due, days_since_full, _last_full_date = _full_recalc_due(
                        now, full_recalc_marker_path, bt_cfg.full_recalc_min_gap_days,
                        daily=bt_cfg.full_recalc_daily)
                    if False and not weekend_full_due:  # ╨║╤А╨░╤В╨║╨╛╨╡ ╤А╨╡╤И╨╡╨╜╨╕╨╡ ╨┐╨╡╤З╨░╤В╨░╨╡╤В _log_recalc_chain()
                        print(f"  тД╣я╕П  ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╤Г╨╢╨╡ ╨▒╤Л╨╗ ({days_since_full} ╨┤╨╜. ╨╜╨░╨╖╨░╨┤ / ╨▓ ╤В╨╡╨║╤Г╤Й╨╡╨╝ ╨╛╨║╨╜╨╡ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е) тАФ ╨┐╨╛╨▓╤В╨╛╤А╨╜╨╛ ╨Э╨Х ╨╖╨░╨┐╤Г╤Б╨║╨░╨╡╨╝. "
                              + (" ╨Ц╨┤╤С╨╝ ╨╛╤В╨║╤А╤Л╤В╨╕╤П ╤А╤Л╨╜╨║╨░ (╨Я╨╜) тАФ ╤В╨╛╤А╨│╨╛╨▓╨╗╨╕ ╨▓ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╨╡ ╨╜╨╡╤В." if now.weekday() >= 5 else " ╨а╨░╨▒╨╛╤В╨░╨╡╨╝ ╨▓ ╨╛╨▒╤Л╤З╨╜╨╛╨╝ ╤А╨╡╨╢╨╕╨╝╨╡ (╨╝╨╛╨╜╨╕╤В╨╛╤А╨╕╨╜╨│ ╤Б╨╕╨│╨╜╨░╨╗╨╛╨▓)."))
                else:
                    # ╨Э╨╡ ╨╝╨╛╨╢╨╡╨╝ ╨┐╨╛╨┤╤В╨▓╨╡╤А╨┤╨╕╤В╤М, ╤З╤В╨╛ ╤Б╨╡╨│╨╛╨┤╨╜╤П ╤Г╨╢╨╡ ╤Б╤З╨╕╤В╨░╨╗╨╕ тАФ ╤Б╤З╨╕╤В╨░╨╡╨╝ ╨╖╨░╨╜╨╛╨▓╨╛
                    weekend_full_due = True
            except (OSError, ValueError, json.JSONDecodeError):
                weekend_full_due = True
        # ╨Я╨╛╨╗╨╜╤Л╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨┤╨╡╤А╨╢╨╕╤В ╨▒╨╛╨╡╨▓╨╛╨╣ ╤Ж╨╕╨║╨╗ ╨╖╨░╨║╤А╤Л╤В╤Л╨╝ 150тАУ230 ╨╝╨╕╨╜: ╨┐╨╛╨║╨░ ╨╛╨╜ ╨╕╨┤╤С╤В,
        # ╨▒╨░╤А╤Л/╤Б╨╕╨│╨╜╨░╨╗╤Л/╤В╤А╨╡╨╣╨╗╨╕╨╜╨│ ╨╜╨╡ ╨┐╤А╨╛╨▓╨╡╤А╤П╤О╤В╤Б╤П. full_recalc_only_flat=True тАФ ╨╛╤В╨╗╨╛╨╢╨╕╤В╤М.
        # ╨Ф╨╜╤С╨╝ ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╛╤В╨║╨╗╨░╨┤╤Л╨▓╨░╨╡╨╝ ╨┤╨╛ ╨╜╨╛╤З╨╜╨╛╨│╨╛ ╨╛╨║╨╜╨░ (╨║╤А╨╛╨╝╨╡ ╨┐╨╡╤А╨▓╨╛╨│╨╛ ╨╖╨░╨┐╤Г╤Б╨║╨░).
        if (weekend_full_due and not is_first_run
                and not _in_full_window(now, bt_cfg.full_refresh_window_end_hour,
                                        bt_cfg.night_backtest_hour)):
            print(f"  тП╕  ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╛╤В╨╗╨╛╨╢╨╡╨╜ ╨┤╨╛ ╨╜╨╛╤З╨╜╨╛╨│╨╛ ╨╛╨║╨╜╨░ "
                  f"({bt_cfg.night_backtest_hour}:00тАУ{bt_cfg.full_refresh_window_end_hour}:00): "
                  f"╤Б╨╡╨╣╤З╨░╤Б {now.strftime('%H:%M')} тАФ ╤А╨░╨▒╨╛╤В╨░╨╡╨╝ ╨╜╨░ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╤Е")
            weekend_full_due = False
        if weekend_full_due and _has_open_positions():
            if bt_cfg.full_recalc_only_flat:
                print("  тП╕  ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╛╤В╨╗╨╛╨╢╨╡╨╜: ╨╡╤Б╤В╤М ╨╛╤В╨║╤А╤Л╤В╤Л╨╡ ╨┐╨╛╨╖╨╕╤Ж╨╕╨╕ "
                      "(full_recalc_only_flat=True)")
                weekend_full_due = False
            else:
                print("  тЪая╕П  ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨┐╤А╨╕ ╨╛╤В╨║╤А╤Л╤В╤Л╤Е ╨┐╨╛╨╖╨╕╤Ж╨╕╤П╤Е: ╨┐╨╛╨║╨░ ╨╕╨┤╤С╤В ╤А╨░╤Б╤З╤С╤В, "
                      "╨▒╨░╤А╤Л ╨╕ ╤Б╨╕╨│╨╜╨░╨╗╤Л ╨╜╨╡ ╨┐╤А╨╛╨▓╨╡╤А╤П╤О╤В╤Б╤П", flush=True)
        if is_first_run or weekend_full_due:
            FORCE_RECALC = True
            weekend_full_due = True
            # ╨д╨╛╨╜╨╛╨▓╤Л╨╣ ╤А╨╡╨╢╨╕╨╝: ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╤А╨╛╤Е╨╛╨┤ ╤Б╤В╨░╨▓╨╕╨╝ ╨▓ ╤Д╨╛╨╜, ╨░ ╤Б╤В╨░╤А╤В╤Г╨╡╨╝ ╨╜╨░ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╤Е тАФ ╨╕╨╜╨░╤З╨╡
            # ╤А╨╡╤Б╤В╨░╤А╤В ╨▓╨╜╤Г╤В╤А╨╕ ╨╜╨╛╤З╨╜╨╛╨│╨╛ ╨╛╨║╨╜╨░ ╤Б╨╜╨╛╨▓╨░ ╨▓╤Б╤В╨░╨╗ ╨▒╤Л ╨╜╨░ 150тАУ230 ╨╝╨╕╨╜. ╨б╨╕╨╜╤Е╤А╨╛╨╜╨╜╨╛ ╨╛╤Б╤В╨░╨▓╨╗╤П╨╡╨╝
            # ╨┐╨╡╤А╨▓╤Л╨╣ ╨╖╨░╨┐╤Г╤Б╨║ (╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨╛╨▓ ╨╡╤Й╤С ╨╜╨╡╤В) ╨╕ ╤А╤Г╤З╨╜╨╛╨╣ full_recalc_mode.
            if (getattr(bt_cfg, 'async_backtest', False)
                    and not is_first_run and not manual_full):
                _bg_start(bt_cfg.symbols, symbol_data, strategy_params, bt_cfg)
                FORCE_RECALC = False
                weekend_full_due = False
                _bg_started = True      # ╤З╨╡╤Б╤В╨╜╨░╤П ╤Б╤В╤А╨╛╨║╨░ ╤А╨╡╤И╨╡╨╜╨╕╤П ╨╜╨╕╨╢╨╡: ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╤А╨╛╤Е╨╛╨┤ ╤Г╨╢╨╡ ╨▓ ╤Д╨╛╨╜╨╡
                print(f"  ЁЯЪА ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨┐╨╛╤Б╤В╨░╨▓╨╗╨╡╨╜ ╨▓ ╤Д╨╛╨╜ "
                      f"({backtest_worker_count(bt_cfg)} ╨┐╤А╨╛╤Ж╨╡╤Б╤Б╨╛╨▓) тАФ ╤Б╤В╨░╤А╤В ╨╜╨░ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╤Е, "
                      f"╤А╨╡╨╖╤Г╨╗╤М╤В╨░╤В ╨┐╤А╨╕╨╝╨╡╨╜╨╕╤В╤Б╤П ╨┐╨╛ ╨╖╨░╨▓╨╡╤А╤И╨╡╨╜╨╕╨╕")
            else:
                print(f"  ЁЯМЩ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ({now.strftime('%A')} {now.strftime('%Y-%m-%d %H:%M')}) тАФ ╨╛╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е / ╨┤╨╛╨│╨╛╨╜")

        # тФАтФА ╨а╤Г╤З╨╜╨╛╨╣ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В (full_recalc_mode=True) тАФ ╤В╨╛╨╢╨╡ ╨▓ ╤Д╨╛╨╜ тФАтФА
        # ╨а╨░╨╜╤М╤И╨╡ ╤А╤Г╤З╨╜╨╛╨╣ ╤А╨╡╨╢╨╕╨╝ ╨▓╤Б╨╡╨│╨┤╨░ ╤И╤С╨╗ ╤Б╨╕╨╜╤Е╤А╨╛╨╜╨╜╨╛ ╨╕ ╨┤╨╡╤А╨╢╨░╨╗ ╨▒╨╛╨╡╨▓╨╛╨╣ ╤Ж╨╕╨║╨╗ ╨╖╨░╨║╤А╤Л╤В╤Л╨╝
        # 150тАУ230 ╨╝╨╕╨╜. ╨в╨╡╨┐╨╡╤А╤М ╨┐╤А╨╕ async_backtest ╨╛╨╜ ╤Б╤В╨░╨▓╨╕╤В╤Б╤П ╤Д╨╛╨╜╨╛╨▓╤Л╨╝ job (╨║╨░╨║ ╨╜╨╛╤З╨╜╨╛╨╣):
        # ╤Ж╨╕╨║╨╗ ╨┐╤А╨╛╨┤╨╛╨╗╨╢╨░╨╡╤В ╤В╨╛╤А╨│╨╛╨▓╨░╤В╤М, ╤А╨╡╨╖╤Г╨╗╤М╤В╨░╤В ╨┐╤А╨╕╨╝╨╡╨╜╤П╨╡╤В╤Б╤П ╨┐╨╛ ╨╖╨░╨▓╨╡╤А╤И╨╡╨╜╨╕╨╕.
        if manual_full and not _bg_started:
            if getattr(bt_cfg, 'async_backtest', False) and not is_first_run:
                _bg_start(bt_cfg.symbols, symbol_data, strategy_params, bt_cfg)
                _bg_started = True
                manual_full = False      # ╤Б╤В╨░╤А╤В╨╛╨▓╤Л╨╣ ╨┐╤А╨╛╨│╨╛╨╜ ╨╜╨╕╨╢╨╡ тАФ ╤А╨╡╤А╨░╨╜╨║ ╨┐╨╛ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╨╝
                FORCE_RECALC = False
                print(f"  ЁЯЪА ╨а╨г╨з╨Э╨Ю╨Щ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨┐╨╛╤Б╤В╨░╨▓╨╗╨╡╨╜ ╨▓ ╤Д╨╛╨╜ "
                      f"({backtest_worker_count(bt_cfg)} ╨┐╤А╨╛╤Ж╨╡╤Б╤Б╨╛╨▓) тАФ ╤Ж╨╕╨║╨╗ ╨╜╨╡ ╨▒╨╗╨╛╨║╨╕╤А╤Г╨╡╤В╤Б╤П")
            else:
                print("  ЁЯМЩ ╨а╨г╨з╨Э╨Ю╨Щ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В тАФ ╤Б╨╕╨╜╤Е╤А╨╛╨╜╨╜╨╛ (async_backtest ╨▓╤Л╨║╨╗╤О╤З╨╡╨╜ "
                      "╨╕╨╗╨╕ ╤Н╤В╨╛ ╨┐╨╡╤А╨▓╤Л╨╣ ╨╖╨░╨┐╤Г╤Б╨║ ╨▒╨╡╨╖ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨╛╨▓)")
        
            
            

    # ╨Ь╨░╤А╨║╨╡╤А╨░ ╨╜╨╡╤В (╨╜╨░╨┐╤А. ╤Б╤А╨░╨╖╤Г ╨┐╨╛╤Б╨╗╨╡ ╨╛╨▒╨╜╨╛╨▓╨╗╨╡╨╜╨╕╤П) тАФ ╤Д╨╕╨║╤Б╨╕╤А╤Г╨╡╨╝ ╨╗╤Г╤З╤И╤Г╤О ╨╕╨╖╨▓╨╡╤Б╤В╨╜╤Г╤О ╨┤╨░╤В╤Г,
    # ╤З╤В╨╛╨▒╤Л ╨╜╨╡ ╨╖╨░╨┐╤Г╤Б╨║╨░╤В╤М ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ┬л╨▓╤Б╨╗╨╡╨┐╤Г╤О┬╗ ╨╜╨░ ╨║╨░╨╢╨┤╨╛╨╝ ╤Б╤В╨░╤А╤В╨╡.
    if not os.path.exists(full_recalc_marker_path):
        _seed = _read_last_full_recalc(full_recalc_marker_path)
        if _seed is not None:
            _write_full_recalc_marker(full_recalc_marker_path,
                                      ts=datetime.combine(_seed, datetime.min.time()))

    _log_recalc_chain(now, night_reset_path, full_recalc_marker_path, is_first_run,
                      bt_cfg.full_recalc_min_gap_days, days_since_full, weekend_full_due or _bg_started, manual_full)

    if manual_full:
        print("  тЪЩя╕П  full_recalc_mode=True тАФ ╨а╨г╨з╨Э╨Ю╨Щ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨Я╨Х╨а╨Х╨б╨з╨Б╨в ╨▓╤Б╨╡╤Е ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╣")
    elif is_first_run:
        print("  ЁЯЖХ ╨Э╨╡╤В ╨║╤Н╤И╨░ ╨┐╤А╨╛╤И╨╗╨╛╨│╨╛ ╨┐╤А╨╛╨│╨╛╨╜╨░ тАФ ╤Б╤З╨╕╤В╨░╨╡╨╝ ╨Т╨б╨Х ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╕ ╤Б ╨╜╤Г╨╗╤П")
    else:
        print("  тЬЕ ╨Х╤Б╤В╤М ╨║╤Н╤И ╨┐╤А╨╛╤И╨╗╨╛╨│╨╛ ╨┐╤А╨╛╨│╨╛╨╜╨░ тАФ ╨╕╤Б╨┐╨╛╨╗╤М╨╖╤Г╨╡╨╝ ╤З╨╡╨║╨┐╨╛╨╕╨╜╤В╤Л (╤А╨░╨▒╨╛╤В╨░ ╨┐╨╛ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╨╝)")

    try:
        # ╨Ь╨░╤А╨║╨╡╤А ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ ╨╖╨┤╨╡╤Б╤М ╨Э╨Х ╨┐╨╕╤И╨╡╨╝: ╨╡╨│╨╛ ╨┤╨▓╨╕╨│╨░╨╡╤В ╤Б╨░╨╝ run_full_backtest,
        # ╨╕ ╤В╨╛╨╗╤М╨║╨╛ ╨╡╤Б╨╗╨╕ ╨┐╤А╨╛╨│╨╛╨╜ ╨┐╨╛╨║╤А╤Л╨╗ ╨┐╨╗╨░╨╜ ╨╜╨░ 100%. ╨а╨░╨╜╤М╤И╨╡ ╨╝╨░╤А╨║╨╡╤А ╤Б╤В╨░╨▓╨╕╨╗╤Б╤П ╨Ч╨Р╨а╨Р╨Э╨Х╨Х тАФ
        # ╨╕ ╤Г╨┐╨░╨▓╤И╨╕╨╣/╨╜╨╡╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╤А╨╛╨│╨╛╨╜ ╨╝╨╛╨╗╤З╨░ ┬л╤Б╤К╨╡╨┤╨░╨╗┬╗ ╤Б╨╗╨╡╨┤╤Г╤О╤Й╤Г╤О ╨╜╨╛╤З╤М.
        #
        # ╨Я╤А╨╡╨┤╨▓╨░╤А╨╕╤В╨╡╨╗╤М╨╜╨╛╨╣ ╨╖╨░╨┐╨╕╤Б╨╕ ╨╝╨░╤А╨║╨╡╤А╨░ ╨╖╨┤╨╡╤Б╤М ╨▒╨╛╨╗╤М╤И╨╡ ╨╜╨╡╤В (╤Б╨╝. ╨▓╤Л╤И╨╡).
        # ╨Ф╤Г╨▒╨╗╤М ╨╖╨░╨┐╨╕╤Б╨╕ ╨╝╨░╤А╨║╨╡╤А╨░ ╤Г╨▒╤А╨░╨╜ 27.10
        all_top, all_results = run_full_backtest(
            bt_cfg.symbols, symbol_data, strategy_params, bt_cfg,
            test_strategy=None,
            test_mode=False,
            force_recalc=FORCE_RECALC or manual_full or weekend_full_due,
            incremental=False,   # ╨Ш╨Э╨Ъ╨а╨Х╨Ь╨Х╨Э╨в ╨г╨Ф╨Р╨Ы╨Б╨Э: ╤В╨╛╨╗╤М╨║╨╛ ╨┐╨╛╨╗╨╜╤Л╨╡ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╤Л
            is_night_run=is_first_run or manual_full or weekend_full_due
        )

        # ╨Я╨╛╤Б╨╗╨╡ ╨┐╨╡╤А╨▓╨╛╨│╨╛ ╨┐╤А╨╛╨│╨╛╨╜╨░ ╨╖╨░╨┐╨╕╤Б╤Л╨▓╨░╨╡╨╝ night_reset.json
        if is_first_run or manual_full or weekend_full_due:
            _write_night_reset(night_reset_path, start_time, len(bt_cfg.symbols), len(all_results))
            # ╨Ь╨░╤А╨║╨╡╤А ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╡╨│╨╛ ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ (╤А╨╡╤А╨░╨╜╨║╨╕ ╤Н╤В╨╛╤В ╤Д╨░╨╣╨╗ ╨╜╨╡ ╤В╤А╨╛╨│╨░╤О╤В)
            # ╨Ь╨░╤А╨║╨╡╤А ╨┤╨▓╨╕╨│╨░╨╡╤В ╤Б╨░╨╝ ╨┐╤А╨╛╨│╨╛╨╜: ╨╖╨┤╨╡╤Б╤М ╤В╨╛╨╗╤М╨║╨╛ ╨┐╤А╨╛╨▓╨╡╤А╤П╨╡╨╝, ╤З╤В╨╛ ╨╛╨╜ ╨╡╨│╨╛ ╨╖╨░╤Б╨╗╤Г╨╢╨╕╨╗.
            import functions as _fn_mk
            if getattr(_fn_mk, 'LAST_RUN_KIND', None) == 'full':
                _write_full_recalc_marker(full_recalc_marker_path)
            else:
                print("  тЪая╕П  ╨Ь╨░╤А╨║╨╡╤А ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ ╨╜╨╡ ╤Б╨┤╨▓╨╕╨│╨░╤О: ╨┐╤А╨╛╨│╨╛╨╜ ╨╜╨╡ ╨┐╨╛╨║╤А╤Л╨╗ "
                      "╨┐╨╗╨░╨╜ тАФ ╤Б╨╗╨╡╨┤╤Г╤О╤Й╨╡╨╣ ╨╜╨╛╤З╤М╤О ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨┐╨╛╨▓╤В╨╛╤А╨╕╤В╤Б╤П", flush=True)

    except Exception as exc:
        print(f"\n[╨Ъ╨а╨Ш╨в╨Ш╨з╨Э╨Ю] ╨Я╨╡╤А╨▓╤Л╨╣ ╨▒╤Н╨║╤В╨╡╤Б╤В ╨╜╨╡ ╨╖╨░╨▓╨╡╤А╤И╨╕╨╗╤Б╤П: {exc!r}", flush=True)
        print("╨б╨╛╤Е╤А╨░╨╜╨╡╨╜╤Л ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л ╨│╨╛╤В╨╛╨▓╤Л╤Е ╤Б╨╕╨╝╨▓╨╛╨╗╨╛╨▓ тАФ ╨┐╨╛╨▓╤В╨╛╤А╨╜╤Л╨╣ ╨╖╨░╨┐╤Г╤Б╨║ ╨┐╤А╨╛╨┤╨╛╨╗╨╢╨╕╤В ╤Б ╨╜╨╕╤Е.", flush=True)
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
        print(f"╨б╤З╤С╤В: {acc.login} | ╨б╨╡╤А╨▓╨╡╤А: {acc.server} | ╨Т╨░╨╗╤О╤В╨░: {acc.currency} | ╨а╨╡╨╢╨╕╨╝: {mode_name}")
    print(f"╨С╨░╨╗╨░╨╜╤Б: {balance:.0f} ╤А╤Г╨▒ | ╨Ъ╨▓╨╛╤В╨░ ╤А╨╕╤Б╨║╨░: {balance * risk_cfg.max_risk_pct:.0f} ╤А╤Г╨▒ | ╨Я╨╛╤А╨╛╨│ score >= {risk_cfg.min_score}")

    deduped_results = all_results
    print(f"╨Я╨╛╤Б╨╗╨╡ ╨┤╨╡╨┤╤Г╨┐╨╗╨╕╨║╨░╤Ж╨╕╨╕: {len(deduped_results)} ╨║╨╛╨╝╨▒╨╕╨╜╨░╤Ж╨╕╨╣")

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
    # ╨и╤В╤Г╤А╨▓╨░╨╗ ╨╜╨╕╨╢╨╡ ╨┐╨╡╤А╨╡╨╗╨╛╨╢╨╕╤В ╨╗╨╛╤В╤Л ╨╡╤Й╤С ╤А╨░╨╖ ╨╕ ╨┐╤А╨╕╨╝╨╡╨╜╨╕╤В ╤В╨╕╨╗╤М╤В ╨┐╨╛╨▓╤В╨╛╤А╨╜╨╛ (╨╕╨┤╨╡╨╝╨┐╨╛╤В╨╡╨╜╤В╨╜╨╛),
    # ╨╜╨╛ ╨╡╤Б╨╗╨╕ ╤И╤В╤Г╤А╨▓╨░╨╗ ╨╜╨╡ ╨╛╤В╤А╨░╨▒╨╛╤В╨░╨╡╤В (╨╜╨╡╤В ╨║╨▓╨╛╤В/╨▒╤О╨┤╨╢╨╡╤В╨░), ╨┐╨╗╨░╨╜ ╨▓╤Б╤С ╤А╨░╨▓╨╜╨╛ ╨┤╨╛╨╗╨╢╨╡╨╜
    # ╨╜╨╡╤Б╤В╨╕ ╨╜╨░╨┤╨▒╨░╨▓╨║╤Г тАФ ╨╕╨╜╨░╤З╨╡ ╨┤╤Н╤И╨▒╨╛╤А╨┤ ╨┐╨╛╨║╨░╨╢╨╡╤В ┬л╤Б╤Л╤А╨╛╨╣┬╗ ╨╛╨▒╤К╤С╨╝.
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

    print(f"╨Р╨║╤В╨╕╨▓╨╕╤А╨╛╨▓╨░╨╜╨╛ {len(active)} ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╣ ╨╕╨╖ {len(deduped_results)} ╨║╨╛╨╝╨▒╨╕╨╜╨░╤Ж╨╕╨╣")

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
            risk_cfg, steering_cfg, journal_dir=JOURNAL_DIR, tag='(╤Б╤В╨░╤А╤В)')
        if _wheel_st.get('changed') or _wheel_st.get('synced'):
            write_active_state(active, active_strategies, balance,
                               risk_cfg.max_risk_pct, JOURNAL_DIR)
    else:
        print("  [WHEEL] ╨Ю╨в╨Ъ╨Ы╨о╨з╨Б╨Э: steering_cfg.enabled=False тАФ ╨║╨▓╨╛╤В╤Л/╨╗╨╛╤В╤Л ╨╜╨╡ ╨┐╨╡╤А╨╡╤Б╤З╨╕╤В╤Л╨▓╨░╤О╤В╤Б╤П.",
              flush=True)

    # тФАтФА ╨Ю╨┤╨╜╨╛╨║╤А╨░╤В╨╜╤Л╨╣ ╨Ф╨Ю╨У╨Ю╨Э ╨╕╤Б╤В╨╛╤А╨╕╨╕ ╤Б╨┤╨╡╨╗╨╛╨║ ╨┐╤А╨╕ ╤Б╤В╨░╤А╤В╨╡ (╨▓ ╤Д╨╛╨╜╨╡) тФАтФА
    # ╨и╨╕╤А╨╛╨║╨╛╨╡ ╨╛╨║╨╜╨╛ (30 ╤Б╤Г╤В╨╛╨║) ╨╖╨░╨║╤А╤Л╨▓╨░╨╡╤В ╨┤╤Л╤А╤Л, ╨╜╨░╨║╨╛╨┐╨╗╨╡╨╜╨╜╤Л╨╡ ╨┐╤А╨╛╤Б╤В╨╛╨╡╨╝ ╨▒╨╛╤В╨░/╨╝╨░╤И╨╕╨╜╤Л ╨╕╨╗╨╕
    # ╨┐╤А╨╡╨╢╨╜╨╕╨╝ ┬л╤Б╨╢╨╕╨╝╨░╤О╤Й╨╕╨╝╤Б╤П┬╗ ╨╛╨║╨╜╨╛╨╝ ingest (╤Б╨┤╨╡╨╗╨║╨░ 20.10 16:45 ╨╜╨╡ ╨┐╨╛╨┐╨░╨╗╨░ ╨╕╨╝╨╡╨╜╨╜╨╛ ╤В╨░╨║).
    # ╨Ш╨┤╨╡╨╝╨┐╨╛╤В╨╡╨╜╤В╨╜╨╛ (UPSERT ╨┐╨╛ deal_ticket), ╨╕╨┤╤С╤В ╨▓ ╤Д╨╛╨╜╨╡ тАФ ╤Ж╨╕╨║╨╗ ╨╜╨╡ ╨╖╨░╨┤╨╡╤А╨╢╨╕╨▓╨░╨╡╤В╤Б╤П.
    _ingest_start(days=30, verbose=True)

    print(f"\n╨Ч╨░╨┐╤Г╤Б╨║ ╤Ж╨╕╨║╨╗╨░. Ctrl+F2 ╨┤╨╗╤П ╨╛╤Б╤В╨░╨╜╨╛╨▓╨║╨╕.\n")
    if now.weekday() >= 5 and not weekend_full_due:
        print("тП│ ╨Т╤Л╤Е╨╛╨┤╨╜╨╛╨╣: ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╤Г╨╢╨╡ ╨▒╤Л╨╗ ╨▓╤Л╨┐╨╛╨╗╨╜╨╡╨╜ ╤А╨░╨╜╨╡╨╡ тАФ ╨┐╨╛╨▓╤В╨╛╤А╨╜╨╛ ╨Э╨Х ╤Б╤З╨╕╤В╨░╨╡╨╝.\n"
              "   ╨а╨╡╨╢╨╕╨╝ ╨╛╨╢╨╕╨┤╨░╨╜╨╕╤П ╨╛╤В╨║╤А╤Л╤В╨╕╤П ╤А╤Л╨╜╨║╨░ (╨Я╨╜). ╨в╨╛╤А╨│╨╛╨▓╨╗╨╕ ╨▓ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╨╡ ╨╜╨╡╤В.\n")
    print("тЬЕ " + ('╨Ь╨╕╨╜╨╕╨╝╨░╨╗╤М╨╜╤Л╨╣ ╤А╨╡╨╢╨╕╨╝ ╤А╨░╨▒╨╛╤В╤Л тАФ ╨╢╨┤╤С╨╝ ╨╛╤В╨║╤А╤Л╤В╨╕╤П ╤А╤Л╨╜╨║╨░ (╨Я╨╜).' if now.weekday() >= 5 else '╨Ч╨░╨┐╤Г╤Й╨╡╨╜ ╤А╨░╨▒╨╛╤З╨╕╨╣ ╤Ж╨╕╨║╨╗ (╨╝╨╛╨╜╨╕╤В╨╛╤А╨╕╨╜╨│ ╤Б╨╕╨│╨╜╨░╨╗╨╛╨▓ ╨╕ ╨╕╤Б╨┐╨╛╨╗╨╜╨╡╨╜╨╕╨╡).') + "\n"
          "   ╨Т ╨▒╤Г╨┤╨╜╨╕: ╨╝╨╛╨╜╨╕╤В╨╛╤А╨╕╨╜╨│ ╤Б╨╕╨│╨╜╨░╨╗╨╛╨▓. ╨Ю╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е: ╨╛╨┤╨╕╨╜ ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В (╤Б ╨┤╨╛╨│╨╛╨╜╨╛╨╝ ╨▓ ╨▒╤Г╨┤╨╜╨╕, ╨╡╤Б╨╗╨╕ ╤Г╨╕╨║-╤Н╨╜╨┤ ╨┐╤А╨╛╨┐╤Г╤Й╨╡╨╜).\n")

    # тХРтХРтХР ╨У╨Ы╨Р╨Т╨Э╨л╨Щ ╨ж╨Ш╨Ъ╨Ы тХРтХРтХР
    last_full_backtest_date = None  # ╨╜╨╡ ┬л╤Б╨╡╨│╨╛╨┤╨╜╤П┬╗: ╨╜╨╛╤З╨╜╨╛╨╣ ╤А╨╡-╤А╨░╨╜╨║ (╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л+╤И╤В╤Г╤А╨▓╨░╨╗) ╨┤╨╛╨╗╨╢╨╡╨╜ ╨╛╤В╤А╨░╨▒╨╛╤В╨░╤В╤М ╨╕ ╨▓ ╨┤╨╡╨╜╤М ╤А╨╡╤Б╤В╨░╤А╤В╨░
    last_mode_check = datetime.now().date()
    last_state_write = datetime.now()
    # ╨и╤В╤Г╤А╨▓╨░╨╗: ╨▓╤А╨╡╨╝╤П ╨┐╨╛╤Б╨╗╨╡╨┤╨╜╨╡╨│╨╛ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ ╨║╨▓╨╛╤В/╨┐╨╡╤А╨╡╨║╨╗╨░╨┤╨║╨╕ ╨╗╨╛╤В╨╛╨▓ (╨╜╨╡ ╨╖╨░╨▓╨╕╤Б╨╕╤В ╨╛╤В ╨▒╤Н╨║╤В╨╡╤Б╤В╨░).
    # ╨Э╨░ ╤Б╤В╨░╤А╤В╨╡ ╤И╤В╤Г╤А╨▓╨░╨╗ ╤Г╨╢╨╡ ╨╛╤В╤А╨░╨▒╨╛╤В╨░╨╗ ╨▓╤Л╤И╨╡ тЖТ ╨╛╤В╤Б╤З╤С╤В interval_sec ╨╕╨┤╤С╤В ╨╛╤В ╤В╨╡╨║╤Г╤Й╨╡╨│╨╛ ╨╝╨╛╨╝╨╡╨╜╤В╨░.
    last_steering = datetime.now() if steering_cfg.enabled else datetime.min
    last_journal_write = datetime.now()
    journal_month = datetime.now().strftime('%Y%m')
    last_ticks_time = datetime.now()
    last_conn_warn_time = datetime.min
    last_balance_refresh = datetime.now()
    last_quota_recalc = datetime.now()
    last_equity_sample = datetime.min          # ╤Б╤Н╨╝╨┐╨╗╨╡╤А floating тЖТ trades_db (daily_peak/equity_samples)
    last_trades_ingest = datetime.min          # ╨┤╨╛╨▒╨╛╤А ╤Б╨┤╨╡╨╗╨╛╨║ ╨▓ trades_db (deals) ╨▓ ╤В╨╡╤З╨╡╨╜╨╕╨╡ ╨┤╨╜╤П
    EQUITY_SAMPLE_INTERVAL_SEC = 300           # ╤Б╨▓╨╛╨╣ ╨╕╨╜╤В╨╡╤А╨▓╨░╨╗ ╤Б╤Н╨╝╨┐╨╗╨╕╨╜╨│╨░, ╨╜╨╡╨╖╨░╨▓╨╕╤Б╨╕╨╝ ╨╛╤В poll_interval
    # ╨Ф╨╛╨▒╨╛╤А ╤Б╨┤╨╡╨╗╨╛╨║ ╨▓ trades_db (deals): ╨╖╨░╨║╤А╤Л╤В╨╕╤П ╨┐╨╕╤И╤Г╤В╤Б╤П ╤Б╤А╨░╨╖╤Г (strategy_engine._record_close тЖТ
    # trades_db.record_position), ╨╜╨╛ ╤Б╤В╤А╨░╤Е╨╛╨▓╨╛╤З╨╜╤Л╨╣ ingest ╨╜╤Г╨╢╨╡╨╜ ╨╕ ╨┤╨╜╤С╨╝, ╨░ ╨╜╨╡ ╤В╨╛╨╗╤М╨║╨╛ ╨▓ 3:00.
    TRADES_DB_INGEST_INTERVAL_SEC = 900        # 15 ╨╝╨╕╨╜
    def _net_cashflow(since_dt):
        """╨з╨╕╤Б╤В╤Л╨╣ ╨▓╨╜╨╡╤И╨╜╨╕╨╣ ╨║╤Н╤И╤Д╨╗╨╛╤Г (╨┐╨╛╨┐╨╛╨╗╨╜╨╡╨╜╨╕╤П тИТ ╨▓╤Л╨▓╨╛╨┤╤Л) ╨▓ ╤А╤Г╨▒╨╗╤П╤Е ╤Б ╨╝╨╛╨╝╨╡╨╜╤В╨░ since_dt.
        ╨Э╤Г╨╢╨╡╨╜, ╤З╤В╨╛╨▒╤Л ╨│╨▓╨░╤А╨┤╤Л ╤А╨╕╤Б╨║╨░ ╨╜╨╡ ╨┐╤А╨╕╨╜╨╕╨╝╨░╨╗╨╕ ╨┤╨╡╨┐╨╛/╨▓╤Л╨▓╨╛╨┤ ╨╖╨░ ╤В╨╛╤А╨│╨╛╨▓╤Л╨╣ ╤Г╨▒╤Л╤В╨╛╨║."""
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
    daily_stop_notified = False  # [STOP] ╨┐╨╡╤З╨░╤В╨░╨╡╨╝ ╨╕ ╨╖╨░╨║╤А╤Л╨▓╨░╨╡╨╝ ╨┐╨╛╨╖╨╕╤Ж╨╕╨╕ ╨╛╨┤╨╕╨╜ ╤А╨░╨╖ ╨╖╨░ ╨┤╨╡╨╜╤М
    first_run = True  # ╨д╨╗╨░╨│ ╨┐╨╡╤А╨▓╨╛╨│╨╛ ╨╖╨░╨┐╤Г╤Б╨║╨░ тАФ ╨╜╤Г╨╢╨╡╨╜ ╨┤╨╗╤П ╨┐╨╛╨╗╨╜╨╛╨│╨╛ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░

    try:
        while True:
            now = datetime.now()

            # тФАтФА ╨б╤Н╨╝╨┐╨╗╨╡╤А ╨╜╨╡╤А╨╡╨░╨╗╨╕╨╖╨╛╨▓╨░╨╜╨╜╨╛╨╣ ╨┐╤А╨╕╨▒╤Л╨╗╨╕ (trades_db): ╤Б╨▓╨╛╨╣ ╨╕╨╜╤В╨╡╤А╨▓╨░╨╗ ~300 ╤Б тФАтФА
            # ╨в╨╛╤А╨│╨╛╨▓╤Г╤О ╨╗╨╛╨│╨╕╨║╤Г ╨╜╨╡ ╤В╤А╨╛╨│╨░╨╡╨╝: ╤В╨╛╨╗╤М╨║╨╛ ╨┐╨╕╤И╨╡╨╝ floating ╨┐╨╛ ╨║╨░╤В╨╡╨│╨╛╤А╨╕╤П╨╝ ╨▓ daily_peak
            # ╨╕ ╤Б╨╜╨╕╨╝╨╛╨║ ╤Б╤З╤С╤В╨░ ╨▓ equity_samples. Fail-safe тАФ ╨╛╤И╨╕╨▒╨║╨░ ╨С╨Ф ╨╜╨╡ ╤А╨╛╨╜╤П╨╡╤В ╨┐╨░╨╣╨┐╨╗╨░╨╣╨╜.
            if (now - last_equity_sample).total_seconds() >= EQUITY_SAMPLE_INTERVAL_SEC:
                last_equity_sample = now
                try:
                    import trades_db
                    trades_db.sample_positions(interval=EQUITY_SAMPLE_INTERVAL_SEC)
                    # тФАтФА ╨Я╨╕╨║-╤В╤А╨╕╨╝: ╤Д╨╕╨║╤Б╨░╤Ж╨╕╤П ╨┐╨╛ ╨Ш╨б╨в╨Ю╨а╨Ш╨з╨Х╨б╨Ъ╨Ю╨Ь╨г ╨┐╨╕╨║╤Г тВ╜/╨╗╨╛╤В тФАтФАтФАтФАтФАтФАтФАтФАтФАтФА
                    # ╨Ш╨┤╤С╤В ╤Б╤А╨░╨╖╤Г ╨┐╨╛╤Б╨╗╨╡ ╤Б╤Н╨╝╨┐╨╗╨╡╤А╨░ (╨┐╨╕╨║╨╕ ╤Г╨╢╨╡ ╤Б╨▓╨╡╨╢╨╕╨╡). ╨Я╨╛ ╤Г╨╝╨╛╨╗╤З╨░╨╜╨╕╤О
                    # ╨в╨Х╨Э╨Х╨Т╨Ю╨Щ ╤А╨╡╨╢╨╕╨╝: ╤В╨╛╨╗╤М╨║╨╛ ╨╗╨╛╨│ `[TRIM] would тАж` + ╨╖╨░╨┐╨╕╤Б╤М ╤А╨╡╤И╨╡╨╜╨╕╤П
                    # ╨▓ peak_trim; ╤А╨╡╨░╨╗╤М╨╜╤Л╨╡ ╨╖╨░╨║╤А╤Л╤В╨╕╤П ╨▓╨║╨╗╤О╤З╨░╤О╤В╤Б╤П ╨▓ config.PeakTrimParams
                    # (enabled=True). Fail-safe: ╨╛╤И╨╕╨▒╨║╨░ ╨╜╨╡ ╤А╨╛╨╜╤П╨╡╤В ╨╜╨╕ ╤Б╤Н╨╝╨┐╨╗╨╡╤А, ╨╜╨╕ ╤Ж╨╕╨║╨╗.
                    try:
                        import peak_trim
                        peak_trim.scan_and_trim()
                    except Exception as _trim_err:
                        print(f"  [WARN] peak_trim: {_trim_err!r}", flush=True)
                except Exception as _smp_err:
                    print(f"  [WARN] trades_db.sample: {_smp_err!r}", flush=True)

            # тФАтФА ╨Ф╨╛╨▒╨╛╤А ╤Б╨┤╨╡╨╗╨╛╨║ ╨▓ trades_db (deals) тАФ ╨▓ ╨д╨Ю╨Э╨Х, ╤Ж╨╕╨║╨╗ ╨╜╨╡ ╨▒╨╗╨╛╨║╨╕╤А╤Г╨╡╤В╤Б╤П тФАтФА
            # ╨Ч╨░╨║╤А╤Л╤В╨╕╤П ╨╕ ╤В╨░╨║ ╨┐╨╕╤И╤Г╤В╤Б╤П ╤Б╤А╨░╨╖╤Г (_record_close тЖТ trades_db.record_position),
            # ╨╜╨╛ ╤Н╤В╨╛ ╤Б╤В╤А╨░╤Е╨╛╨▓╨║╨░ ╨╛╤В ╨┐╤А╨╛╨┐╤Г╤Б╨║╨╛╨▓ (╤А╨╡╤Б╤В╨░╤А╤В, ╨╖╨░╨║╤А╤Л╤В╨╕╨╡ ┬л╨╜╨╡ ╨╜╨░╤И╨╡╨╣┬╗ ╤А╤Г╨║╨╛╨╣).
            if (now - last_trades_ingest).total_seconds() >= TRADES_DB_INGEST_INTERVAL_SEC:
                last_trades_ingest = now
                try:
                    import trades_db
                    _ingest_start(days=1)     # ╤Д╨╛╨╜: MT5-╨╖╨░╨┐╤А╨╛╤Б ╨╕ ╨╖╨░╨┐╨╕╤Б╤М ╨▓ ╨С╨Ф ╨╜╨╡ ╤В╨╛╤А╨╝╨╛╨╖╤П╤В ╤Ж╨╕╨║╨╗
                    if _ingest_error:         # ╨╛╤И╨╕╨▒╨║╨░ ╨┐╤А╨╡╨┤╤Л╨┤╤Г╤Й╨╡╨│╨╛ ╤Д╨╛╨╜╨╛╨▓╨╛╨│╨╛ ╨┤╨╛╨▒╨╛╤А╨░
                        print(f"  [WARN] trades_db.ingest: {_ingest_error}", flush=True)
                        _ingest_error = None
                except Exception as _ing_err:
                    print(f"  [WARN] trades_db.ingest: {_ing_err!r}", flush=True)

            # ╨б╨╝╨╡╨╜╨░ ╨┤╨╜╤П
            if now.date() != last_mode_check:
                last_mode_check = now.date()
                print(f"\n[{now}] ╨Э╨╛╨▓╤Л╨╣ ╨┤╨╡╨╜╤М")
                if now.weekday() >= 5:  # ╨б╨▒=5, ╨Т╤Б=6
                    print("  тД╣ ╨а╨░╤Б╤З╤С╤В╤Л ╨╖╨░╨▓╨╡╤А╤И╨╡╨╜╤Л. ╨Ю╨╢╨╕╨┤╨░╨╜╨╕╨╡ ╨╛╤В╨║╤А╤Л╤В╨╕╤П ╤А╤Л╨╜╨║╨░ (╨Я╨╜) тАФ ╨╝╨╕╨╜╨╕╨╝╨░╨╗╤М╨╜╤Л╨╣ ╤А╨╡╨╢╨╕╨╝.")

            # ╨Э╨╛╤З╨╜╨╛╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В: ╤А╨░╨╖ ╨▓ ╤Б╤Г╤В╨║╨╕ ╤Б 3:00 (╨▒╤Г╨┤╨╜╨╕ тАФ ╨╕╨╜╨║╤А╨╡╨╝╨╡╨╜╤В, ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╨╡ тАФ ╨Я╨Ю╨Ы╨Э╨л╨Щ)
            # ╨С╤Г╨┤╨╜╨╕ тАФ ╤А╨╡╤А╨░╨╜╨║ ╨┐╨╛ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╨╝ (+╨╕╨╜╨║╤А╨╡╨╝╨╡╨╜╤В); ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╨╡ тАФ ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В
            # ╨Т╤Л╤Е╨╛╨┤╨╜╨╛╨╣ ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╤Г╨┐╤А╨░╨▓╨╗╤П╨╡╤В╤Б╤П auto_weekend_recalc (True ╨┐╨╛ ╤Г╨╝╨╛╨╗╤З╨░╨╜╨╕╤О)
            is_weekday = now.weekday() < 5  # ╨Я╨╜=0 ... ╨Я╤В=4
            is_weekend = now.weekday() >= 5  # ╨б╨▒=5, ╨Т╤Б=6
            
            # ╨Э╨╛╤З╨╜╨╛╨╣ ╨┐╤А╨╛╨│╨╛╨╜: ╤А╨░╨╖ ╨▓ ╨┤╨╡╨╜╤М ╨┐╨╛╤Б╨╗╨╡ 3:00, ╨┐╨╛╨▓╤В╨╛╤А╨╜╨╛ ╨▓ ╤В╨╛╤В ╨╢╨╡ ╨┤╨╡╨╜╤М ╨╜╨╡ ╨╖╨░╨┐╤Г╤Б╨║╨░╨╡╤В╤Б╤П
            # force_recalc=True (╨┐╨╛╨╗╨╜╤Л╨╣) ╤Б╤В╨░╨▓╨╕╤В╤Б╤П ╤В╨╛╨╗╤М╨║╨╛ ╨╜╨░ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е; ╨▓ ╨▒╤Г╨┤╨╜╨╕ тАФ ╤А╨╡╤А╨░╨╜╨║
            
            # тФАтФА ╨д╨╛╨╜╨╛╨▓╤Л╨╣ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В: ╨┐╤А╨╕╤С╨╝ ╤А╨╡╨╖╤Г╨╗╤М╤В╨░╤В╨░ тФАтФА
            # Job ╤Б╤З╨╕╤В╨░╨╗╤Б╤П ╨▓ ╨╛╤В╨┤╨╡╨╗╤М╨╜╨╛╨╝ ╨┐╨╛╤В╨╛╨║╨╡: ╤Ж╨╕╨║╨╗ ╨▓╤Б╤С ╤Н╤В╨╛ ╨▓╤А╨╡╨╝╤П ╨╢╨╕╨╗ ╨╛╨▒╤Л╤З╨╜╨╛╨╣ ╨╢╨╕╨╖╨╜╤М╤О
            # (╤В╨╕╨║╨╕, ╨▒╨░╤А╤Л, ╤Б╨╕╨│╨╜╨░╨╗╤Л, ╤В╤А╨╡╨╣╨╗╨╕╨╜╨│, ╨░╨▓╨░╤А╨╕╨╣╨╜╤Л╨╡ ╨╖╨░╤Й╨╕╤В╤Л). ╨Я╤А╨╕╨╝╨╡╨╜╤П╨╡╨╝ ╨╡╨│╨╛ ╤А╨╡╨╖╤Г╨╗╤М╤В╨░╤В
            # ╤В╨╡╨╝ ╨╢╨╡ ╨┐╤Г╤В╤С╨╝, ╤З╤В╨╛ ╨╕ ╤Б╨╕╨╜╤Е╤А╨╛╨╜╨╜╤Л╨╣ ╨╜╨╛╤З╨╜╨╛╨╣ ╨┐╤А╨╛╨│╨╛╨╜ (╤Б╨╝. ╨▒╨╗╨╛╨║ ╨╜╨╕╨╢╨╡).
            _bg_finished = _bg_poll()
            if _bg_finished and _bg_failed is not None:
                print(f"\n  тЪая╕П  ╨д╨╛╨╜╨╛╨▓╤Л╨╣ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╜╨╡ ╤Г╨┤╨░╨╗╤Б╤П: {_bg_failed} тАФ "
                      f"╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л ╨╝╨╛╨│╤Г╤В ╨▒╤Л╤В╤М ╨╛╨▒╨╜╨╛╨▓╨╗╨╡╨╜╤Л ╤З╨░╤Б╤В╨╕╤З╨╜╨╛, ╨┐╨╛╨▓╤В╨╛╤А╨╕╨╝ ╤Б╨╗╨╡╨┤╤Г╤О╤Й╨╡╨╣ ╨╜╨╛╤З╤М╤О",
                      flush=True)
                last_full_backtest_date = now.date()
                # ╨Я╨░╨┤╨╡╨╜╨╕╨╡ ╤Д╨╛╨╜╨╛╨▓╨╛╨│╨╛ job тАФ ╤В╨╛╨╢╨╡ ╤Б╨╛╨▒╤Л╤В╨╕╨╡ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░: ╨┐╨╕╤И╨╡╨╝ ╤Б╤В╤А╨╛╨║╤Г
                # kind='incomplete', ╤З╤В╨╛╨▒╤Л ╨▓╨╛ ╨▓╨║╨╗╨░╨┤╨║╨╡ Backtest ╨▒╤Л╨╗╨░ ╨Ю╨а╨Р╨Э╨Ц╨Х╨Т╨Р╨п ╤В╨╛╤З╨║╨░,
                # ╨░ ╨╜╨╡ ╨┐╤Г╤Б╤В╨╛╤В╨░ (╨╝╨╛╨╗╤З╨░╨╗╨╕╨▓╤Л╨╣ ╨┐╤А╨╛╨▓╨░╨╗ тАФ ╤В╨╛, ╨╕╨╖-╨╖╨░ ╤З╨╡╨│╨╛ ╤Н╤В╨╛ ╤В╤П╨╜╤Г╨╗╨╛╤Б╤М ╨╜╨╡╨┤╨╡╨╗╤П╨╝╨╕).
                try:
                    from functions import append_backtest_history as _abh
                    _abh(_bg_elapsed_min * 60.0, 0, 0, 0, kind='incomplete',
                         is_night_run=True, combos_done=0, combos_plan=0,
                         symbols_total=len(bt_cfg.symbols), coverage_pct=0.0,
                         ok=False, error=str(_bg_failed)[:300])
                except Exception as _je:
                    print(f"  [WARN] ╨╢╤Г╤А╨╜╨░╨╗ ╨┐╤А╨╛╨│╨╛╨╜╨╛╨▓: {_je!r}", flush=True)
            elif _bg_ready:
                print(f"\n[{now.strftime('%H:%M:%S')}] тЬЕ ╨д╨╛╨╜╨╛╨▓╤Л╨╣ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╖╨░╨▓╨╡╤А╤И╤С╨╜ "
                      f"({_bg_elapsed_min:.0f} ╨╝╨╕╨╜) тАФ ╨┐╤А╨╕╨╝╨╡╨╜╤П╤О ╤А╨╡╨╖╤Г╨╗╤М╤В╨░╤В, ╤Ж╨╕╨║╨╗ ╨╜╨╡ ╨╛╤Б╤В╨░╨╜╨░╨▓╨╗╨╕╨▓╨░╨╗╤Б╤П",
                      flush=True)

            should_run_backtest = False
            if _bg_ready:
                # ╨а╨╡╨╖╤Г╨╗╤М╤В╨░╤В ╤Д╨╛╨╜╨╛╨▓╨╛╨│╨╛ job ╨│╨╛╤В╨╛╨▓ тЖТ ╨╕╨┤╤С╨╝ ╨╜╨╛╤З╨╜╤Л╨╝ ╨┐╤Г╤В╤С╨╝: ╤Б╤З╨╕╤В╨░╤В╤М ╨╜╨╡╤З╨╡╨│╨╛,
                # ╤Б╨▓╨╡╨╢╨╕╨╡ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л ╤Г╨╢╨╡ ╨╜╨░ ╨┤╨╕╤Б╨║╨╡ (╤Б╨╝. _bg_apply ╨▓╨╜╤Г╤В╤А╨╕ ╨▒╨╗╨╛╨║╨░ ╨╜╨╕╨╢╨╡).
                should_run_backtest = True
            elif now.hour >= bt_cfg.night_backtest_hour and now.date() != last_full_backtest_date:
                should_run_backtest = True
            
            if should_run_backtest:
                # ╨д╨╛╨╜╨╛╨▓╤Л╨╣ job ╨╖╨░╨▓╨╡╤А╤И╨╕╨╗╤Б╤П тЖТ ╤А╨╡╨╖╤Г╨╗╤М╤В╨░╤В ╨┐╤А╨╕╨╝╨╡╨╜╤П╨╡╨╝ ╨б╨Х╨Щ╨з╨Р╨б: ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л ╤Г╨╢╨╡
                # ╤Б╨▓╨╡╨╢╨╕╨╡, ╨┐╨╡╤А╨╡╤Б╤З╨╕╤В╤Л╨▓╨░╤В╤М ╨╜╨╡╤З╨╡╨│╨╛ (╤Б╨╝. force_recalc ╨╜╨╕╨╢╨╡). ╨д╨╗╨░╨│ ╨┐╨╡╤А╨╡╨╜╨╛╤Б╨╕╨╝ ╨▓
                # ╨╗╨╛╨║╨░╨╗╤М╨╜╤Г╤О ╨┐╨╡╤А╨╡╨╝╨╡╨╜╨╜╤Г╤О, ╤З╤В╨╛╨▒╤Л _bg_ready ╨╜╨╡ ┬л╨╖╨░╨╗╨╕╨┐╨░╨╗┬╗ ╨╜╨░ ╤Б╨╗╨╡╨┤╤Г╤О╤Й╨╕╨╡ ╨╜╨╛╤З╨╕:
                # _bg_apply ╨╢╨╕╨▓╤С╤В ╤В╨╛╨╗╤М╨║╨╛ ╤В╨╡╨║╤Г╤Й╤Г╤О ╨╕╤В╨╡╤А╨░╤Ж╨╕╤О ╨╕ ╤А╨╡╤И╨░╨╡╤В: ╤Б╤З╨╕╤В╨░╤В╤М ╨╗╨╕ ╤Н╤В╨╛╤В ╨┐╤А╨╛╨│╨╛╨╜
                # ╨Я╨Ю╨Ы╨Э╨л╨Ь (╨╝╨░╤А╨║╨╡╤А ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░) ╨╕ ╨╜╨░╨┤╨╛ ╨╗╨╕ ╤Б╤В╨░╨▓╨╕╤В╤М ╨╜╨╛╨▓╤Л╨╣ job.
                _bg_apply = _bg_ready
                _bg_ready = False
                
                # auto_weekend_recalc=False тАФ ╨▓ ╨▓╤Л╤Е╨╛╨┤╨╜╨╛╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╜╨╡ ╨╖╨░╨┐╤Г╤Б╨║╨░╨╡╨╝
                if is_weekend and not bt_cfg.auto_weekend_recalc and not _bg_apply:
                    print(f"\n[{now.strftime('%H:%M:%S')}] тП╕ ╨Т╤Л╤Е╨╛╨┤╨╜╨╛╨╣ ({now.strftime('%A')}) тАФ ╨░╨▓╤В╨╛-╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╛╤В╨║╨╗╤О╤З╤С╨╜ (auto_weekend_recalc=False)")
                    last_full_backtest_date = now.date()
                    continue
                
                # ╨Я╨╛╤А╨░ ╨╗╨╕ ╨Я╨Ю╨Ы╨Э╨л╨Щ: ╨╛╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е (╨б╨▒тАУ╨Т╤Б) ╨╗╨╕╨▒╨╛ ╨┤╨╛╨│╨╛╨╜ ╨▓ ╨▒╤Г╨┤╨╜╨╕
                _night_full_due, _, _ = _full_recalc_due(
                    now, full_recalc_marker_path, bt_cfg.full_recalc_min_gap_days,
                    daily=bt_cfg.full_recalc_daily)
                if not bt_cfg.auto_weekend_recalc and not bt_cfg.full_recalc_daily:
                    _night_full_due = False

                # тФАтФА ╨д╨╛╨╜╨╛╨▓╤Л╨╣ job ╤Г╨╢╨╡ ╨╛╤В╤А╨░╨▒╨╛╤В╨░╨╗ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╤А╨╛╤Е╨╛╨┤ тФАтФА
                # ╨д╨╕╨║╤Б╨╕╤А╤Г╨╡╨╝ ╤Н╤В╨╛ ╨║╨░╨║ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В, ╨┤╨░╨╢╨╡ ╨╡╤Б╨╗╨╕ ╨┐╨╛ ╨║╨░╨╗╨╡╨╜╨┤╨░╤А╤О ╨╛╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е
                # ╨╖╨░╨║╤А╤Л╤В╨╛: ╨╕╨╜╨░╤З╨╡ ╨╜╨╡ ╤Б╨┤╨▓╨╕╨╜╨╡╤В╤Б╤П ╨╝╨░╤А╨║╨╡╤А last_full_recalc, ╨╕ ╤Б╨╗╨╡╨┤╤Г╤О╤Й╨╡╨╣ ╨╜╨╛╤З╤М╤О
                # ╤Б╤В╨░╤А╤В╤Г╨╡╤В ╨╡╤Й╤С ╨╛╨┤╨╕╨╜ ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╤А╨╛╤Е╨╛╨┤.
                if _bg_apply:
                    _night_full_due = True

                # тФАтФА ╨Ю╨║╨╜╨╛ ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ тФАтФА
                # ╨б╨╕╨╜╤Е╤А╨╛╨╜╨╜╤Л╨╣ ╤А╨╡╨╢╨╕╨╝ (async_backtest=False): ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨┤╨╡╤А╨╢╨╕╤В ╨▒╨╛╨╡╨▓╨╛╨╣ ╤Ж╨╕╨║╨╗
                # ╨╖╨░╨║╤А╤Л╤В╤Л╨╝ 150тАУ230 ╨╝╨╕╨╜ тАФ ╨▒╨░╤А╤Л ╨╜╨╡ ╨╛╨┐╤А╨░╤И╨╕╨▓╨░╤О╤В╤Б╤П, ╤Б╨╕╨│╨╜╨░╨╗╤Л ╨╜╨╡ ╤А╨╛╨╢╨┤╨░╤О╤В╤Б╤П,
                # ╤В╤А╨╡╨╣╨╗╨╕╨╜╨│ ╨╕ ╨░╨▓╨░╤А╨╕╨╣╨╜╤Л╨╡ ╨╖╨░╤Й╨╕╤В╤Л (daily loss, equity stop, margin) ╨╜╨╡ ╤А╨░╨▒╨╛╤В╨░╤О╤В.
                # ╨Я╨╛╤Н╤В╨╛╨╝╤Г ╨┤╨╜╤С╨╝ ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╤А╨╛╤Е╨╛╨┤ ╨╛╤В╨║╨╗╨░╨┤╤Л╨▓╨░╨╡╤В╤Б╤П ╨┤╨╛ ╨╜╨╛╤З╨╜╨╛╨│╨╛ ╨╛╨║╨╜╨░ (╤Б╨╝. ╨╜╨╕╨╢╨╡).
                # ╨Т ╤Д╨╛╨╜╨╛╨▓╨╛╨╝ ╤А╨╡╨╢╨╕╨╝╨╡ (async_backtest=True) ╤Ж╨╕╨║╨╗ ╨╜╨╡ ╨▒╨╗╨╛╨║╨╕╤А╤Г╨╡╤В╤Б╤П, ╨┐╨╛╤Н╤В╨╛╨╝╤Г
                # ╨╛╨│╤А╨░╨╜╨╕╤З╨╡╨╜╨╕╨╡ ╨┐╨╛ ╨▓╤А╨╡╨╝╨╡╨╜╨╕ ╤Б╤Г╤В╨╛╨║ ╤Б╤В╨░╨╜╨╛╨▓╨╕╤В╤Б╤П ╨╝╤П╨│╨║╨╕╨╝: ╨┤╨╜╤С╨╝ ╨▒╨╡╤А╤С╨╝ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л,
                # ╨░ ╨┐╨╛╨╗╨╜╤Л╨╣ ╨┐╤А╨╛╤Е╨╛╨┤ ╤Г╤Е╨╛╨┤╨╕╤В ╨▓ ╨╜╨╛╤З╨╜╨╛╨╡ ╨╛╨║╨╜╨╛.
                if not _bg_apply and not _in_full_window(now, bt_cfg.full_refresh_window_end_hour, bt_cfg.night_backtest_hour):
                # (╨▓ ╤Д╨╛╨╜╨╛╨▓╨╛╨╝ ╤А╨╡╨╢╨╕╨╝╨╡ ╨╛╨║╨╜╨╛ ╨╜╨╡ ╨║╤А╨╕╤В╨╕╤З╨╜╨╛ тАФ ╤Ж╨╕╨║╨╗ ╨▓╤Б╤С ╤А╨░╨▓╨╜╨╛ ╨╜╨╡ ╨▓╤Б╤В╨░╨╜╨╡╤В)
                # ╨Ю╨║╨╜╨╛ ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░: 3:00тАУ10:00 ╨▓ ╨▒╤Г╨┤╨╜╨╕; ╨▓ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╨╡ тАФ ╨▒╨╡╨╖ ╨╛╨│╤А╨░╨╜╨╕╤З╨╡╨╜╨╕╤П.
                    if _night_full_due:
                        print(f"  тП╕  ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╛╤В╨╗╨╛╨╢╨╡╨╜ ╨┤╨╛ ╨╜╨╛╤З╨╜╨╛╨│╨╛ ╨╛╨║╨╜╨░ "
                              f"({bt_cfg.night_backtest_hour}:00тАУ{bt_cfg.full_refresh_window_end_hour}:00): "
                              f"╤Б╨╡╨╣╤З╨░╤Б {now.strftime('%H:%M')} тАФ ╤А╨░╨▒╨╛╤В╨░╨╡╨╝ ╨┐╨╛ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╨╝")
                    _night_full_due = False
                if _night_full_due and not _bg_apply and _has_open_positions():
                    if bt_cfg.full_recalc_only_flat:
                        print("  тП╕  ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╛╤В╨╗╨╛╨╢╨╡╨╜: ╨╡╤Б╤В╤М ╨╛╤В╨║╤А╤Л╤В╤Л╨╡ ╨┐╨╛╨╖╨╕╤Ж╨╕╨╕ "
                              "(full_recalc_only_flat=True) тАФ ╨▓ ╤Н╤В╨╛╤В ╤Ж╨╕╨║╨╗ ╤А╨░╨▒╨╛╤В╨░╨╡╨╝ ╨┐╨╛ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╨╝")
                        _night_full_due = False
                    else:
                        print("  тЪая╕П  ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨┐╤А╨╕ ╨╛╤В╨║╤А╤Л╤В╤Л╤Е ╨┐╨╛╨╖╨╕╤Ж╨╕╤П╤Е: ╨┐╨╛╨║╨░ ╨╕╨┤╤С╤В ╤А╨░╤Б╤З╤С╤В, "
                              "╨▒╨░╤А╤Л ╨╕ ╤Б╨╕╨│╨╜╨░╨╗╤Л ╨╜╨╡ ╨┐╤А╨╛╨▓╨╡╤А╤П╤О╤В╤Б╤П", flush=True)

                # ╨Ю╨┐╤А╨╡╨┤╨╡╨╗╤П╨╡╨╝ ╨┐╤А╨╕╤З╨╕╨╜╤Г ╨╖╨░╨┐╤Г╤Б╨║╨░
                if _night_full_due:
                    _reason = " тАФ ╤А╨╡╨╖╤Г╨╗╤М╤В╨░╤В ╤Д╨╛╨╜╨╛╨▓╨╛╨│╨╛ job" if _bg_apply else " тАФ ╨╛╨║╨╜╨╛ ╨▓╤Л╤Е╨╛╨┤╨╜╤Л╤Е / ╨┤╨╛╨│╨╛╨╜..."
                    print(f"\n[{now.strftime('%H:%M:%S')}] тП║ ╨Э╨╛╤З╨╜╨╛╨╣ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ({now.strftime('%A')}){_reason}")
                elif is_weekday:
                    print(f"\n[{now.strftime('%H:%M:%S')}] ЁЯФД ╨Э╨╛╤З╨╜╨╛╨╣ ╨а╨Х╨а╨Р╨Э╨Ъ: ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л + ╤И╤В╤Г╤А╨▓╨░╨╗ (╤Б╨╡╤В╨║╤Г ╨╜╨╡ ╨┐╨╡╤А╨╡╤Б╤З╨╕╤В╤Л╨▓╨░╨╡╨╝)")
                else:
                    print(f"\n[{now.strftime('%H:%M:%S')}] тП║ ╨Т╤Л╤Е╨╛╨┤╨╜╨╛╨╣ ({now.strftime('%A')}) тАФ ╤А╨╡╤А╨░╨╜╨║ ╨┐╨╛ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╨╝ (╤Б╨╡╤В╨║╤Г ╨╜╨╡ ╨┐╨╡╤А╨╡╤Б╤З╨╕╤В╤Л╨▓╨░╨╡╨╝)")

                try:
                    # тФАтФА ╨д╨╛╨╜╨╛╨▓╤Л╨╣ (async) ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В: ╤Ж╨╕╨║╨╗ ╨▒╨╛╨╗╤М╤И╨╡ ╨╜╨╡ ╨▒╨╗╨╛╨║╨╕╤А╤Г╨╡╤В╤Б╤П тФАтФА
                    # ╨С╤Л╨╗╨╛: run_full_backtest тАФ ╤Б╨╕╨╜╤Е╤А╨╛╨╜╨╜╤Л╨╣ ╨▓╤Л╨╖╨╛╨▓, 150тАУ230 ╨╝╨╕╨╜╤Г╤В ╨▒╨╛╨╡╨▓╨╛╨╣ ╤Ж╨╕╨║╨╗
                    # ╤Б╤В╨╛╤П╨╗. ╨б╤В╨░╨╗╨╛: ╤В╤П╨╢╤С╨╗╨░╤П ╤З╨░╤Б╤В╤М ╤Б╤З╨╕╤В╨░╨╡╤В╤Б╤П ╨▓ ╨╛╤В╨┤╨╡╨╗╤М╨╜╨╛╨╝ ╨┐╨╛╤В╨╛╨║╨╡
                    # (backtest_job.BacktestJob), ╨░ ╤А╨╡╨╖╤Г╨╗╤М╤В╨░╤В ╨┐╤А╨╕╨╝╨╡╨╜╤П╨╡╤В╤Б╤П ╨┐╨╛ ╨╖╨░╨▓╨╡╤А╤И╨╡╨╜╨╕╨╕ job тАФ
                    # ╤Б╨╗╨╡╨┤╤Г╤О╤Й╨╡╨╣ ╨╕╤В╨╡╤А╨░╤Ж╨╕╨╡╨╣, ╨┐╨╛╨▓╤В╨╛╤А╨╜╤Л╨╝ ╨▓╤Е╨╛╨┤╨╛╨╝ ╨▓ ╤Н╤В╨╛╤В ╨▒╨╗╨╛╨║ ╨┐╨╛ _bg_ready.
                    if (getattr(bt_cfg, 'async_backtest', False)
                            and _night_full_due and not _bg_apply):
                        if _bg_running():
                            print(f"  тП│ ╨д╨╛╨╜╨╛╨▓╤Л╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╤Г╨╢╨╡ ╨╕╨┤╤С╤В тАФ ╨╜╨╛╨▓╤Л╨╣ ╨╜╨╡ ╤Б╤В╨░╨▓╨╗╤О", flush=True)
                        else:
                            _bg_start(bt_cfg.symbols, symbol_data, strategy_params, bt_cfg)
                            print(f"  ЁЯЪА ╨д╨╛╨╜╨╛╨▓╤Л╨╣ ╨Я╨Ю╨Ы╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨┐╨╛╤Б╤В╨░╨▓╨╗╨╡╨╜ "
                                  f"({backtest_worker_count(bt_cfg)} ╨┐╤А╨╛╤Ж╨╡╤Б╤Б╨╛╨▓, ╨┐╤А╨╕╨╛╤А╨╕╤В╨╡╤В below normal) тАФ "
                                  f"╨▒╨╛╨╡╨▓╨╛╨╣ ╤Ж╨╕╨║╨╗ ╨┐╤А╨╛╨┤╨╛╨╗╨╢╨░╨╡╤В ╤А╨░╨▒╨╛╤В╨░╤В╤М", flush=True)
                        last_full_backtest_date = now.date()
                        continue

                    _, all_results = run_full_backtest(
                        bt_cfg.symbols, symbol_data, strategy_params, bt_cfg,
                        test_strategy=None,
                        test_mode=False,
                        # ╨д╨╛╨╜╨╛╨▓╤Л╨╣ job ╤Г╨╢╨╡ ╨┐╤А╨╛╨│╤А╨╡╨╗ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л тЖТ ╨┐╨╡╤А╨╡╤Б╤З╨╕╤В╤Л╨▓╨░╤В╤М ╨╜╨╡╤З╨╡╨│╨╛: ╤З╨╕╤В╨░╨╡╨╝
                        # ╨│╨╛╤В╨╛╨▓╨╛╨╡ (╤А╨╡╤А╨░╨╜╨║ ╨┐╨╛ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╨╝, ~1 ╤Б). ╨Ш╨╜╨░╤З╨╡ тАФ ╨╛╨▒╤Л╤З╨╜╤Л╨╣ ╤Б╨╕╨╜╤Е╤А╨╛╨╜╨╜╤Л╨╣ ╨┐╤Г╤В╤М.
                        force_recalc=(bool(_night_full_due) and not _bg_apply),
                        is_night_run=True
                    )
                except Exception as exc:
                    print(f"\n[WARN] ╨Э╨╛╤З╨╜╨╛╨╣ ╨┐╨╡╤А╨╡╤А╨░╤Б╤З╤С╤В ╨╜╨╡ ╤Г╨┤╨░╨╗╤Б╤П: {exc!r} тАФ "
                          f"╨╛╤Б╤В╨░╨▓╨╗╤П╨╡╨╝ ╤В╨╡╨║╤Г╤Й╨╕╨╡ ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╕, ╨┐╨╛╨▓╤В╨╛╤А╨╕╨╝ ╨╖╨░╨▓╤В╤А╨░ ╨▓ 3:00.", flush=True)
                    # ╨Я╤А╨╛╨▓╨░╨╗ ╨▓╨╕╨┤╨╡╨╜ ╨▓╨╛ ╨▓╨║╨╗╨░╨┤╨║╨╡ Backtest (╨╛╤А╨░╨╜╨╢╨╡╨▓╨░╤П ╤В╨╛╤З╨║╨░), ╨░ ╨╜╨╡ ╤В╨╛╨╗╤М╨║╨╛ ╨▓ ╨╗╨╛╨│╨╡.
                    if _night_full_due:
                        try:
                            from functions import append_backtest_history as _abh
                            _abh(0.0, 0, 0, 0, kind='incomplete', is_night_run=True,
                                 combos_done=0, combos_plan=0,
                                 symbols_total=len(bt_cfg.symbols), coverage_pct=0.0,
                                 ok=False, error=str(exc)[:300])
                        except Exception as _je:
                            print(f"  [WARN] ╨╢╤Г╤А╨╜╨░╨╗ ╨┐╤А╨╛╨│╨╛╨╜╨╛╨▓: {_je!r}", flush=True)
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
                # ╨в╨░ ╨╢╨╡ ╨╗╨╛╨│╨╕╨║╨░, ╤З╤В╨╛ ╨▓ run_steering_wheel ╨╜╨╕╨╢╨╡ (╤В╨░╨╝ тАФ ╨┤╨╗╤П ╨╗╨╛╤В╨╛╨▓ ╤И╤В╤Г╤А╨▓╨░╨╗╨░);
                # ╨╖╨┤╨╡╤Б╤М тАФ ╤З╤В╨╛╨▒╤Л ╨┐╨╗╨░╨╜ ╨╜╤С╤Б ╨╜╨░╨┤╨▒╨░╨▓╨║╤Г, ╨┤╨░╨╢╨╡ ╨╡╤Б╨╗╨╕ ╤И╤В╤Г╤А╨▓╨░╨╗ ╨╜╨╡ ╤В╤А╨╛╨╜╨╡╤В ╨╗╨╛╤В╤Л.
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
                print(f"╨С╨░╨╗╨░╨╜╤Б: {balance:.0f} ╤А╤Г╨▒ | ╨Ъ╨▓╨╛╤В╨░: {balance * risk_cfg.max_risk_pct:.0f} ╤А╤Г╨▒ | "
                      f"╨Р╨║╤В╨╕╨▓╨╕╤А╨╛╨▓╨░╨╜╨╛ {len(active)} ╨╕╨╖ {len(deduped_results)} (╨▓╤Б╨╡╨│╨╛ {len(all_results)})")

                # тФАтФА ╨б╤В╤А╨░╤Е╨╛╨▓╨║╨░: ╨┐╤Г╤Б╤В╨╛╨╣ ╨┐╤А╨╛╨│╨╛╨╜ ╨╜╨╡ ╨┤╨╛╨╗╨╢╨╡╨╜ ╤Б╤В╨╕╤А╨░╤В╤М ╨┐╨╗╨░╨╜ тФАтФА
                # ╨Х╤Б╨╗╨╕ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨╜╨╡ ╨┤╨░╨╗ ╨╜╨╕ ╨╛╨┤╨╜╨╛╨╣ ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╕ (╨╜╨╡╤Б╨╛╨▓╨╝╨╡╤Б╤В╨╕╨╝╤Л╨╡/╨┐╤Г╤Б╤В╤Л╨╡ ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л,
                # ╨╜╨╡╤В ╨┤╨░╨╜╨╜╤Л╤Е ╤Б╨╕╨╝╨▓╨╛╨╗╨╛╨▓), ╨┐╤Г╤Б╤В╨╛╨╣ active_state.json ╨┐╨╕╤Б╨░╤В╤М ╨╜╨╡╨╗╤М╨╖╤П: Daily Plan
                # ╨╛╤Б╤В╨░╨▓╨░╨╗╤Б╤П ╨▒╨╡╨╖ ╤Б╤В╤А╨╛╨║, ╨░ ranking.txt ╨╛╨▒╨╜╤Г╨╗╤П╨╗╤Б╤П ╨▓ ┬л0 ╨║╨╛╨╝╨▒╨╕╨╜╨░╤Ж╨╕╨╣┬╗.
                # ╨Я╤А╨╛╨┐╤Г╤Б╨║╨░╨╡╨╝ ╨╕╤В╨╡╤А╨░╤Ж╨╕╤О тАФ ╨┐╤А╨╡╨╢╨╜╨╕╨╣ ╨┐╨╗╨░╨╜ ╨╢╨╕╨▓╤С╤В ╨┤╨╛ ╤Б╨╗╨╡╨┤╤Г╤О╤Й╨╡╨│╨╛ ╨┐╤А╨╛╨│╨╛╨╜╨░.
                if not active and os.path.exists(os.path.join(JOURNAL_DIR, 'active_state.json')):
                    print("  [ERROR] ╨Э╨╛╤З╨╜╨╛╨╣ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В ╨┤╨░╨╗ 0 ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╣ тАФ ╨┐╨╗╨░╨╜ ╨╕ ranking ╨Э╨Х "
                          "╨┐╨╡╤А╨╡╨╖╨░╨┐╨╕╤Б╨░╨╜╤Л (╨┐╤А╨╛╨▓╨╡╤А╤М ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╤Л ╨╕ ╨┤╨░╨╜╨╜╤Л╨╡ ╤Б╨╕╨╝╨▓╨╛╨╗╨╛╨▓)", flush=True)
                    last_full_backtest_date = now.date()
                    continue
                write_ranking(active, all_results, JOURNAL_DIR, bt_cfg.backtest_days, len(active), None)
                sync_active_strategies(active, now, symbol_data, active_strategies,
                                       close_order, get_deal_exit_price, record_trade,
                                       strategy_key, assign_magic, bt_cfg.magic_base, len(active))

                # тФАтФА ╨б╤В╨░╤В╤Г╤Б ╤Б╨╡╨╝╨╡╨╣╤Б╤В╨▓ ╨▓ ╨С╨Ф (╨┐╨╛╤Б╨╗╨╡ ╤А╨╡╤А╨░╨╜╨║╨░): ╤Г╤З╨░╤Б╤В╨╕╨╡ ╨▓ ╤А╤Н╨╜╨║╨╕╨╜╨│╨╡ ╨╕ ╨│╨╛╤В╨╛╨▓╨╜╨╛╤Б╤В╤М тФАтФА
                _record_family_status(all_results, active)

                # тФАтФА ╨и╤В╤Г╤А╨▓╨░╨╗: ╨┐╨╗╨░╨▓╨╜╨╛╨╡ ╨┐╨╡╤А╨╡╤А╨░╤Б╨┐╤А╨╡╨┤╨╡╨╗╨╡╨╜╨╕╨╡ ╨║╨▓╨╛╤В ╨┐╨╛ ╤А╨╡╨░╨╗╤М╨╜╤Л╨╝ ╤Б╨┤╨╡╨╗╨║╨░╨╝ тФАтФА
                if False:  # DEPRECATED: ╨╗╨╛╨│╨╕╨║╨░ ╨▓╤Л╨╜╨╡╤Б╨╡╨╜╨░ ╨▓ run_steering_wheel() (╨▓╤Л╨╖╤Л╨▓╨░╨╡╤В╤Б╤П ╨▒╨╡╨╖╤Г╤Б╨╗╨╛╨▓╨╜╨╛ ╨╜╨╕╨╢╨╡)
                    try:
                        # тФАтФА ╨Ш╤Б╤В╨╛╤З╨╜╨╕╨║: Strategy Tree (╨╛╨║╨╜╨╛ ╨░╨╗╨╗╨╛╨║╨░╤Ж╨╕╨╕ lookback_days) тФАтФА
                        # ╨в╨░ ╨╢╨╡ ╨▓╤Л╨▒╨╛╤А╨║╨░ ╤Б╨┤╨╡╨╗╨╛╨║, ╤З╤В╨╛ ╨╕ ╨▓ ╨┤╨╡╤А╨╡╨▓╨╡/╤И╤В╤Г╤А╨▓╨░╨╗╨╡ ╨┤╤Н╤И╨▒╨╛╤А╨┤╨░:
                        # window тЖТ ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ symbol+family. ╨з╨╕╤Б╨╗╨░ ╤Б╨╛╨▓╨┐╨░╨┤╨░╤О╤В 1-╨▓-1.
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
                    # ╨Я╨╛╨╗╨╕╤В╨╕╨║╨░ ╨┐╨╛╤В╨╡╤А╤М (kill switch): ╨┐╨╛╤А╨╛╨│ ╨▓ ╤А╤Г╨▒╨╗╤П╤Е, ╤А╤Г╨▒╨╗╤С╨▓╨░╤П ╤А╨╕╤Б╨║-╨║╨▓╨╛╤В╨░
                    'quota_rub': balance * risk_cfg.max_risk_pct,
                    'loss_decay': getattr(steering_cfg, 'loss_decay', 0.25),
                    'kill_pnl_pct': getattr(steering_cfg, 'kill_pnl_pct', 0.02),
                    'kill_pnl_rub': getattr(steering_cfg, 'kill_pnl_rub', 0.0),
                    'kill_min_trades': getattr(steering_cfg, 'kill_min_trades', 3),
                                    # ╨╡╤Б╨╗╨╕ gamma ╨╡╤Й╤С ╨╜╨╡╤В ╨▓ cfg тАФ ╨┐╨╛╨┤╤Б╤В╨░╨▓╨╕╨╝ ╨┤╨╡╤Д╨╛╨╗╤В
                                }
                            )

                            with open(quotas_path, 'w', encoding='utf-8') as f:
                                json.dump(new_quotas, f, ensure_ascii=False, indent=2)

                            # тФАтФА ╨Я╤А╨╕╨╜╤В: Strategy Tree тЖТ ╨┐╨╡╤А╨╡╨║╨╗╨░╨┤╨║╨░ ╨╛╨▒╤К╤С╨╝╨░ тФАтФА
                            print(f"\n  [WHEEL] ╨Я╨╡╤А╨╡╤Б╤З╤С╤В ╨║╨▓╨╛╤В (score_mode={steering_cfg.score_mode}) "
                                  f"(╨╛╨║╨╜╨╛ {steering_cfg.lookback_days} ╨┤╨╜.).", flush=True)
                            for _line in format_allocation_report(
                                    metrics, prev_quotas, new_quotas,
                                    steering_cfg.lookback_days,
                                    min_trades=steering_cfg.min_trades,
                                    score_mode=steering_cfg.score_mode):
                                print(_line, flush=True)
                            # ╨Я╨╡╤А╨╡╨║╨╗╨░╨┤╨║╨░ ╨╛╨▒╤К╤С╨╝╨░: ╤В╨╛╨╗╤М╨║╨╛ ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╕ ╨▒╨╡╨╖ ╨╛╤В╨║╤А╤Л╤В╨╛╨╣ ╨┐╨╛╨╖╨╕╤Ж╨╕╨╕
                            # тФАтФА ╨Я╨╡╤А╨╡╨║╨╗╨░╨┤╨║╨░ ╨╗╨╛╤В╨╛╨▓: ╨Р╨С╨б╨Ю╨Ы╨о╨в╨Э╨л╨Щ ╤Ж╨╡╨╗╨╡╨▓╨╛╨╣ ╨╗╨╛╤В тФАтФА
                            # ╨а╨░╨╜╤М╤И╨╡ ╨╗╨╛╤В ╤Г╨╝╨╜╨╛╨╢╨░╨╗╤Б╤П ╨╜╨░ q_new/q_prev, ╨┐╨╛╤Н╤В╨╛╨╝╤Г ╤Б╤В╤А╨░╤В╨╡╨│╨╕╤П ╤Б
                            # ╨╝╨╡╨╗╨║╨╕╨╝ ╨╗╨╛╤В╨╛╨╝ ┬л╨┤╨╛╨│╨╛╨╜╤П╨╗╨░┬╗ ╤Ж╨╡╨╗╨╡╨▓╤Г╤О ╨┤╨╛╨╗╤О ╨╝╨╜╨╛╨╢╨╕╤В╨╡╨╗╨╡╨╝ ╨╕ ╤В╨╛╤А╨╝╨╛╨╖╨╕╨╗╨░
                            # ╨┐╨╡╤А╨╡╨║╨╗╨░╨┤╨║╤Г. ╨в╨╡╨┐╨╡╤А╤М ╤Ж╨╡╨╗╨╡╨▓╨╛╨╣ ╨╗╨╛╤В ╤Б╤З╨╕╤В╨░╨╡╤В╤Б╤П ╨╛╤В ╤А╨╕╤Б╨║-╨║╨▓╨╛╤В╤Л:
                            #     lot_i = (budget ├Ч q_i) / sl_money_i
                            # budget тАФ ╤Б╨▓╨╛╨▒╨╛╨┤╨╜╨░╤П ╤З╨░╤Б╤В╤М ╨║╨▓╨╛╤В╤Л (╨╖╨░ ╨▓╤Л╤З╨╡╤В╨╛╨╝ ╤А╨╕╤Б╨║╨░ ╤Г╨╢╨╡ ╨╛╤В╨║╤А╤Л╤В╤Л╤Е
                            # ╨┐╨╛╨╖╨╕╤Ж╨╕╨╣), ╨┐╨╛╤Н╤В╨╛╨╝╤Г ╬г(lot├Чsl_money) тЙд quota ╨┐╨╛ ╨┐╨╛╤Б╤В╤А╨╛╨╡╨╜╨╕╤О.
                            risk_quota = balance * risk_cfg.max_risk_pct
                            _slm = {}
                            _used_risk = 0.0
                            _free_keys = []
                            _n_in_cat = {}
                            # ╬г score ╤Б╨▓╨╛╨▒╨╛╨┤╨╜╤Л╤Е ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╣ ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ тАФ ╨┤╨╛╨╗╤П ╨▓╨╜╤Г╤В╤А╨╕ ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕
                            # ╤Б╤З╨╕╤В╨░╨╡╤В╤Б╤П ╨┐╨╛ score ╨▒╤Н╨║╤В╨╡╤Б╤В╨░, ╨░ ╨╜╨╡ ╨┐╨╛╤А╨╛╨▓╨╜╤Г (╤А╨╡╤И╨╡╨╜╨╕╨╡ 19.10).
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

                                # Kill switch: ╨║╨░╤В╨╡╨│╨╛╤А╨╕╤П ╤Г╨▒╤Л╤В╨╛╤З╨╜╨░ (╨║╨▓╨╛╤В╨░ 0) тЖТ ╨╜╨╛╨▓╤Л╨╡ ╨▓╤Е╨╛╨┤╤Л ╨╖╨░╨┐╤А╨╡╤Й╨╡╨╜╤Л.
                                if q_new <= 0:
                                    if s.get('enabled', True) or float(s.get('lot') or 0) > 0:
                                        print(f"  [WHEEL] KILL {key}: q=0 тЖТ ╤В╨╛╤А╨│╨╛╨▓╨╗╤П ╨╛╤Б╤В╨░╨╜╨╛╨▓╨╗╨╡╨╜╨░ "
                                              f"(╨║╨░╤В╨╡╨│╨╛╤А╨╕╤П {sid}, ╨╗╨╛╤В {s['lot']:.3f} тЖТ 0)", flush=True)
                                    s['lot'] = 0.0
                                    s['enabled'] = False
                                    s['disabled_reason'] = f'steering: ╨║╨▓╨╛╤В╨░ ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ {sid} = 0 (╨╢╨╕╨▓╨╛╨╣ ╤Г╨▒╤Л╤В╨╛╨║)'
                                    st['killed'] += 1
                                    continue

                                # ╨Т╨╛╨╖╨▓╤А╨░╤В ╨▓ ╤А╨░╨▒╨╛╤В╤Г: ╨║╨░╤В╨╡╨│╨╛╤А╨╕╤П ╤Б╨╜╨╛╨▓╨░ ╨▓ ╨┐╨╗╤О╤Б╨╡
                                if s.get('enabled', True) is False:
                                    print(f"  [WHEEL] ╨▓╨╛╨╖╨▓╤А╨░╤В ╨▓ ╤А╨░╨▒╨╛╤В╤Г: {key} (╨║╨░╤В╨╡╨│╨╛╤А╨╕╤П {sid} ╤Б╨╜╨╛╨▓╨░ ╨▓ ╨┐╨╗╤О╤Б╨╡)", flush=True)
                                    s['enabled'] = True
                                    s.pop('disabled_reason', None)

                                if _m <= 0 or _budget <= 0 or _q_covered <= 0:
                                    continue
                                # ╨Ф╨╛╨╗╤П ╨▓╨╜╤Г╤В╤А╨╕ ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ тАФ ╨┐╨╛ score ╨▒╤Н╨║╤В╨╡╤Б╤В╨░ (╨║╨░╨║ ╨▓
                                # tree_weighted_lots); ╨┐╨╛╤А╨╛╨▓╨╜╤Г тАФ ╤В╨╛╨╗╤М╨║╨╛ ╨╡╤Б╨╗╨╕ score ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ 0.
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
                                          f"(q {q_new:.3f}, score {_sc:.2f}/{_scat:.2f}, ╤А╨╕╤Б╨║ {s['lot'] * _m:,.0f} -> "
                                          f"{new_lot * _m:,.0f} тВ╜)")
                                    s['lot'] = new_lot
                                    changed += 1
                            print(f"  [STEERING] ╨Ъ╨▓╨╛╤В╤Л ╨╛╨▒╨╜╨╛╨▓╨╗╨╡╨╜╤Л: {len(new_quotas)} ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╣, "
                                  f"╨╗╨╛╤В╤Л ╤Б╨║╨╛╤А╤А╨╡╨║╤В╨╕╤А╨╛╨▓╨░╨╜╤Л: {changed}", flush=True)
                            _DEAD_TILT_DUP = """  # ╨┤╤Г╨▒╨╗╤М ╤В╨╕╨╗╤М╤В-╨▒╨╗╨╛╨║╨░ (╨╝╤С╤А╤В╨▓╨░╤П ╨▓╨╡╤В╨║╨░ if False) тАФ ╨╢╨╕╨▓╤С╤В ╨▓ run_steering_wheel
        # ╨Ю╨▒╤К╤С╨╝ ╤Г╨╢╨╡ ╨┐╨╡╤А╨╡╨╗╨╛╨╢╨╡╨╜ ╤И╤В╤Г╤А╨▓╨░╨╗╨╛╨╝ тАФ ╨╖╨┤╨╡╤Б╤М ╨╛╨╜ ╤В╨╛╨╗╤М╨║╨╛ ╨╝╨░╤Б╤И╤В╨░╨▒╨╕╤А╤Г╨╡╤В╤Б╤П ╨┐╨╛ ╨╗╤Г╤З╤И╨╡╨╣/
        # ╤Е╤Г╨┤╤И╨╡╨╣ ╤Б╨▓╤П╨╖╨║╨╡ ┬л╨┐╨░╤А╨░ + ╨┤╨╡╨╜╤М ╨▓╤Л╤Е╨╛╨┤╨░┬╗ ╨╖╨░ ╨╛╨║╨╜╨╛ ╨┤╨╛ 90 ╨┤╨╜╨╡╨╣ (tactic_tilt.py).
        # ╨Ш╨┤╨╡╨╝╨┐╨╛╤В╨╡╨╜╤В╨╜╨╛: ╨┐╨╛╨▓╤В╨╛╤А╨╜╤Л╨╣ ╨▓╤Л╨╖╨╛╨▓ ╤Б ╤В╨╡╨╝ ╨╢╨╡ ╨╝╨╜╨╛╨╢╨╕╤В╨╡╨╗╨╡╨╝ ╨▓╤В╨╛╤А╨╛╨╣ ╤А╨░╨╖ ┬▒20% ╨╜╨╡
        # ╨╜╨░╤З╨╕╤Б╨╗╤П╨╡╤В (╨╝╨░╤А╨║╨╡╤А╤Л tilt_base/tilt_mult), ╨░ ╨╗╨╛╤В ╨╛╤В ╤И╤В╤Г╤А╨▓╨░╨╗╨░ тАФ ╨╜╨╛╨▓╤Л╨╣ ╨▒╨░╨╖╨╕╤Б.
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
                            # ╨и╤В╤Г╤А╨▓╨░╨╗ ╨┐╤А╨░╨▓╨╕╤В active_strategies тАФ ╤Н╤В╨╛ ╨╕ ╨╡╤Б╤В╤М ╨▒╨╛╨╣. ╨з╤В╨╛╨▒╤Л
                            # ╨┤╤Н╤И╨▒╨╛╤А╨┤/active_state.json ╨┐╨╛╨║╨░╨╖╤Л╨▓╨░╨╗╨╕ ╨а╨Х╨Р╨Ы╨м╨Э╨г╨о ╨┐╨╡╤А╨╡╨║╨╗╨░╨┤╨║╤Г (╨░ ╨╜╨╡
                            # ╨┤╨╛╤В╤О╨╜╨╡╨╜╨╜╤Л╨╣ tree-weighting ╨╗╨╛╤В), ╨┐╨╡╤А╨╡╨╜╨╛╤Б╨╕╨╝ ╨╕╤В╨╛╨│ ╤И╤В╤Г╤А╨▓╨░╨╗╨░ ╨╜╨░╨╖╨░╨┤
                            # ╨▓ ╨┐╨╗╨░╨╜ (active). ╨Я╨╛╤Б╨╗╨╡ ╤Н╤В╨╛╨│╨╛ active == active_strategies.
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
                                print(f"  [STEERING] ╨Ы╨╛╤В╤Л ╤Б╨╕╨╜╤Е╤А╨╛╨╜╨╕╨╖╨╕╤А╨╛╨▓╨░╨╜╤Л ╨▓ ╨┐╨╗╨░╨╜ (active): {_synced}", flush=True)
                    except Exception as se:
                        print(f"\n[WARN] ╨Ю╤И╨╕╨▒╨║╨░ ╤И╤В╤Г╤А╨▓╨░╨╗╨░: {se!r} тАФ ╨║╨▓╨╛╤В╤Л ╨╜╨╡ ╨╕╨╖╨╝╨╡╨╜╨╡╨╜╤Л", flush=True)
                write_active_state(active, active_strategies, balance, risk_cfg.max_risk_pct, JOURNAL_DIR)




                # --- ╨╛╨▒╨╜╨╛╨▓╨╗╤П╨╡╨╝ night_reset.json ╨┐╨╛╤Б╨╗╨╡ ╨╜╨╛╤З╨╜╨╛╨│╨╛ ╨┐╨╡╤А╨╡╤А╨░╤Б╤З╤С╤В╨░ ---
                _write_night_reset(night_reset_path, start_time, len(bt_cfg.symbols), len(all_results), ts=now)
                if _night_full_due:
                    # ╨Ь╨░╤А╨║╨╡╤А ╨╖╨┤╨╡╤Б╤М ╨Э╨Х ╤Б╤В╨░╨▓╨╕╨╝: ╨╡╨│╨╛ ╨┤╨▓╨╕╨│╨░╨╡╤В ╤В╨╛╨╗╤М╨║╨╛ run_full_backtest ╨╕ ╤В╨╛╨╗╤М╨║╨╛
                    # ╨┐╤А╨╕ 100% ╨┐╨╛╨║╤А╤Л╤В╨╕╨╕ ╨┐╨╗╨░╨╜╨░. ╨а╨░╨╜╤М╤И╨╡ ╨╛╨╜ ╤Б╤В╨░╨▓╨╕╨╗╤Б╤П ╨▓ ╤Н╤В╨╛╨╣ ╤В╨╛╤З╨║╨╡ ╨▒╨╡╨╖╤Г╤Б╨╗╨╛╨▓╨╜╨╛ тАФ
                    # ╨▓ async-╨▓╨╡╤В╨║╨╡ ╤Н╤В╨╛╤В ╨┐╤А╨╛╨│╨╛╨╜ ╨▓╨╛╨╛╨▒╤Й╨╡ ╨╜╨╕╤З╨╡╨│╨╛ ╨╜╨╡ ╨┐╨╡╤А╨╡╤Б╤З╨╕╤В╤Л╨▓╨░╨╗ (╤А╨╡╤А╨░╨╜╨║ ╨┐╨╛
                    # ╤З╨╡╨║╨┐╨╛╨╣╨╜╤В╨░╨╝), ╨░ ╨╝╨░╤А╨║╨╡╤А ╤Б╨┤╨▓╨╕╨│╨░╨╗╤Б╤П, ╨╕ ╤Б╨╗╨╡╨┤╤Г╤О╤Й╨░╤П ╨╜╨╛╤З╤М ╨╝╨╛╨╗╤З╨░ ╨┐╤А╨╛╨┐╤Г╤Б╨║╨░╨╗╨░╤Б╤М.
                    print("  тД╣ ╨Ь╨░╤А╨║╨╡╤А ╨Я╨Ю╨Ы╨Э╨Ю╨У╨Ю ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ ╨▓╤Л╤Б╤В╨░╨▓╨╗╤П╨╡╤В ╤Б╨░╨╝ ╨┐╤А╨╛╨│╨╛╨╜ "
                          "(╤В╨╛╨╗╤М╨║╨╛ ╨┐╤А╨╕ 100% ╨┐╨╛╨║╤А╤Л╤В╨╕╨╕ ╨┐╨╗╨░╨╜╨░)", flush=True)

                yesterday = now.date() - timedelta(days=1)
                report = generate_daily_report(yesterday)

                # ╨б╨▓╨╡╨╢╨╕╨╣ ╨▒╤Н╨║╤В╨╡╤Б╤В тЖТ ╤И╤В╤Г╤А╨▓╨░╨╗ ╨╛╨▒╤П╨╖╨░╨╜ ╨╛╤В╤А╨░╨▒╨╛╤В╨░╤В╤М ╨▓ ╤Н╤В╨╛╨╝ ╨╢╨╡ ╤Ж╨╕╨║╨╗╨╡
                # (╤Б╨▒╤А╨░╤Б╤Л╨▓╨░╨╡╨╝ ╤В╨░╨╣╨╝╨╡╤А, ╤З╤В╨╛╨▒╤Л ╨┐╨╡╤А╨╕╨╛╨┤╨╕╤З╨╡╤Б╨║╨╕╨╣ ╨▓╤Л╨╖╨╛╨▓ ╨╜╨╕╨╢╨╡ ╨╜╨╡ ╨╢╨┤╨░╨╗ interval_sec).
                last_steering = datetime.min
                print(f"  ╨У╨╛╤В╨╛╨▓╨╛: {len(all_results)} ╨║╨╛╨╝╨▒╨╕╨╜╨░╤Ж╨╕╨╣, {len(active)} ╨░╨║╤В╨╕╨▓╨╜╤Л╤Е")

                # тФАтФА ╨Ш╤Б╤В╨╛╤А╨╕╤П ╤Б╨┤╨╡╨╗╨╛╨║ ╨▓ SQLite (trades_db): ╤И╨░╨│ 1 тАФ ╨╗╨╛╨║╨░╨╗╤М╨╜╨░╤П ╨╖╨░╨┐╨╕╤Б╤М тФАтФА
                # Fail-safe: ╨╗╤О╨▒╨░╤П ╨╛╤И╨╕╨▒╨║╨░ ╨С╨Ф ╨╜╨╡ ╨┤╨╛╨╗╨╢╨╜╨░ ╤А╨╛╨╜╤П╤В╤М ╨┐╨░╨╣╨┐╨╗╨░╨╣╨╜.
                try:
                    import trades_db
                    _ingest_start(days=3)     # ╤В╨╛╤В ╨╢╨╡ ╨д╨Ю╨Э: ╨┤╨╛╨▒╨╛╤А ╨╜╨╡ ╤В╨╛╤А╨╝╨╛╨╖╨╕╤В ╨╜╨╛╤З╨╜╨╛╨╣ ╨▒╨╗╨╛╨║
                except Exception as _tdb_err:
                    print(f"  [WARN] trades_db: {_tdb_err!r}", flush=True)

            # тФАтФА ╨и╤В╤Г╤А╨▓╨░╨╗: ╨Ю╨С╨п╨Ч╨Р╨в╨Х╨Ы╨м╨Э╨л╨Щ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В, ╨Э╨Х ╨┐╤А╨╕╨▓╤П╨╖╨░╨╜ ╨║ ╨╜╨╛╤З╨╜╨╛╨╝╤Г ╨▒╤Н╨║╤В╨╡╤Б╤В╤Г тФАтФА
            # ╨а╨░╨╜╤М╤И╨╡ ╨▒╨╗╨╛╨║ ╨╢╨╕╨╗ ╨▓╨╜╤Г╤В╤А╨╕ `if should_run_backtest:` тЖТ ╨╡╤Б╨╗╨╕ ╨╜╨╛╤З╨╜╨╛╨╣ ╨┐╤А╨╛╨│╨╛╨╜
            # ╨▒╤Л╨╗ ╨┐╤А╨╛╨┐╤Г╤Й╨╡╨╜/╤Г╨┐╨░╨╗, ╤И╤В╤Г╤А╨▓╨░╨╗ ╨╜╨╡ ╤А╨░╨▒╨╛╤В╨░╨╗ ╨▓╨╛╨▓╤Б╨╡. ╨в╨╡╨┐╨╡╤А╤М ╨╛╨╜ ╨╛╤В╤А╨░╨▒╨░╤В╤Л╨▓╨░╨╡╤В
            # ╨┐╤А╨╕ ╤Б╤В╨░╤А╤В╨╡, ╤Б╤А╨░╨╖╤Г ╨┐╨╛╤Б╨╗╨╡ ╨╜╨╛╤З╨╜╨╛╨│╨╛ ╨┐╨╡╤А╨╡╤Б╤З╤С╤В╨░ (╤В╨░╨╝ ╤Б╨▒╤А╨░╤Б╤Л╨▓╨░╨╡╤В╤Б╤П
            # last_steering) ╨╕ ╨┤╨░╨╗╨╡╨╡ ╨║╨░╨╢╨┤╤Л╨╡ steering_cfg.interval_sec.
            _steering_every = int(getattr(steering_cfg, 'interval_sec', 3600) or 3600)
            if not steering_cfg.enabled:
                if last_steering != datetime.min:
                    print("  [WHEEL] ╨Ю╨в╨Ъ╨Ы╨о╨з╨Б╨Э: steering_cfg.enabled=False тАФ ╨║╨▓╨╛╤В╤Л/╨╗╨╛╤В╤Л "
                          "╨╜╨╡ ╨┐╨╡╤А╨╡╤Б╤З╨╕╤В╤Л╨▓╨░╤О╤В╤Б╤П (╤Н╤В╨╛ ╨╡╨┤╨╕╨╜╤Б╤В╨▓╨╡╨╜╨╜╨░╤П ╤А╨░╨╖╤А╨╡╤И╤С╨╜╨╜╨░╤П ╨┐╤А╨╕╤З╨╕╨╜╨░).", flush=True)
                    last_steering = datetime.min
            elif (now - last_steering).total_seconds() >= _steering_every:
                last_steering = now
                _wheel_st = run_steering_wheel(
                    active_strategies, active, symbol_data, balance,
                    risk_cfg, steering_cfg, journal_dir=JOURNAL_DIR,
                    tag=f'(╨┐╨╗╨░╨╜╨╛╨▓╤Л╨╣, ╨║╨░╨╢╨┤╤Л╨╡ {_steering_every // 60} ╨╝╨╕╨╜)')
                if _wheel_st.get('changed') or _wheel_st.get('synced'):
                    write_active_state(active, active_strategies, balance,
                                       risk_cfg.max_risk_pct, JOURNAL_DIR)
                    last_state_write = now

            # ╨Я╨╡╤А╨╕╨╛╨┤╨╕╤З╨╡╤Б╨║╨╛╨╡ ╨╛╨▒╨╜╨╛╨▓╨╗╨╡╨╜╨╕╨╡ ╨▒╨░╨╗╨░╨╜╤Б╨░ (╤А╨░╨╖ ╨▓ ╨╝╨╕╨╜╤Г╤В╤Г)
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
                        daily_stop_notified = False  # ╨╜╨╛╨▓╤Л╨╣ ╨┤╨╡╨╜╤М тАФ ╨╗╨╕╨╝╨╕╤В ╤Б╨╜╨╛╨▓╨░ ╨░╨║╤В╨╕╨▓╨╡╨╜

                    last_balance_refresh = now

                    # тФАтФА ╨Я╤А╨╛╨▓╨╡╤А╨║╨░ 1: Daily stop-loss тФАтФА
                    if daily_start_balance is not None:
                        dl_ok, dl_pct, dl_reason = check_daily_loss_limit(
                            daily_start_balance, equity, risk_cfg.daily_loss_limit_pct,
                            cashflow=(_net_cashflow(daily_start_dt) if daily_start_dt else 0.0),
                        )
                        if not dl_ok:
                            # ╨б╨▒╨╛╨╣ ╤В╨╡╤А╨╝╨╕╨╜╨░╨╗╨░ (╨╜╨╡╤В account_info) тАФ ╨┐╨╛╨╖╨╕╤Ж╨╕╨╕ ╨Э╨Х ╨╖╨░╨║╤А╤Л╨▓╨░╨╡╨╝, ╨╢╨┤╤С╨╝ ╤Б╨╗╨╡╨┤╤Г╤О╤Й╨╡╨╣ ╨┐╤А╨╛╨▓╨╡╤А╨║╨╕
                            if 'account_info not available' in dl_reason:
                                continue
                            # ╨Я╨╡╤З╨░╤В╨░╨╡╨╝ [STOP] ╨╕ ╨╖╨░╨║╤А╤Л╨▓╨░╨╡╨╝ ╨┐╨╛╨╖╨╕╤Ж╨╕╨╕ ╨╛╨┤╨╕╨╜ ╤А╨░╨╖ ╨╖╨░ ╨┤╨╡╨╜╤М
                            if daily_stop_notified:
                                continue
                            daily_stop_notified = True
                            _resume_dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                            print(f"\n  [STOP] Daily loss limit: {dl_reason} тАФ ╤В╨╛╤А╨│╨╛╨▓╨╗╤П ╨╛╤Б╤В╨░╨╜╨╛╨▓╨╗╨╡╨╜╨░ ╨┤╨╛ {_resume_dt.strftime('%d.%m.%Y %H:%M')} (╤Б╨▒╤А╨╛╤Б ╨┤╨╜╨╡╨▓╨╜╨╛╨│╨╛ ╨╗╨╕╨╝╨╕╤В╨░ ╨▓ 00:00)")
                            for key, s in list(active_strategies.items()):
                                if s['position'] is not None:
                                    print(f"  -> ╨Ч╨░╨║╤А╤Л╤В╨╕╨╡ {key} ╨┐╨╛ daily stop-loss")
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
                            print(f"\n  [STOP] Equity stop: {eq_reason} тАФ ╨░╨▓╨░╤А╨╕╨╣╨╜╨░╤П ╨╛╤Б╤В╨░╨╜╨╛╨▓╨║╨░!")
                            for key, s in list(active_strategies.items()):
                                if s['position'] is not None:
                                    print(f"  -> ╨Ч╨░╨║╤А╤Л╤В╨╕╨╡ {key} ╨┐╨╛ equity stop")
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
                        print(f"\n  [STOP] {ml_reason} тАФ ╨░╨▓╨░╤А╨╕╨╣╨╜╨╛╨╡ ╤Б╨╛╨║╤А╨░╤Й╨╡╨╜╨╕╨╡!")
                        for key, s in list(active_strategies.items()):
                            if s['position'] is not None:
                                print(f"  -> ╨Ч╨░╨║╤А╤Л╤В╨╕╨╡ {key} ╨┐╨╛ margin level stop")
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
                                  f"╨▓╤Е╨╛╨┤ ╨▒╨╗╨╛╨║╨╕╤А╤Г╨╡╤В ╨│╨╡╨╣╤В ╨║╨▓╨╛╤В╤Л ╨║╨░╤В╨╡╨│╨╛╤А╨╕╨╕ "
                                  f"(strategy_engine.quota_gate_check), ╨╖╨┤╨╡╤Б╤М тАФ ╤В╨╛╨╗╤М╨║╨╛ ╨┐╤А╨╡╨┤╤Г╨┐╤А╨╡╨╢╨┤╨╡╨╜╨╕╨╡")

            # ╨в╨╕╨║╨╕
            ticks = {}
            for sym in bt_cfg.symbols:
                try:
                    t = mt5.symbol_info_tick(sym)
                    if t is not None:
                        ticks[sym] = (t.bid, t.ask)
                except Exception as e:
                    print(f"\n[WARN] ╨Ю╤И╨╕╨▒╨║╨░ ╨┐╨╛╨╗╤Г╤З╨╡╨╜╨╕╤П ╤В╨╕╨║╨░ {sym}: {e!r}", flush=True)

            if not ticks:
                idle_sec = (now - last_ticks_time).total_seconds()
                if (idle_sec >= bt_cfg.connection_timeout_sec
                        and (now - last_conn_warn_time).total_seconds() >= bt_cfg.connection_warn_every_sec):
                    print(f"\n[{now}] ╨Т╨Э╨Ш╨Ь╨Р╨Э╨Ш╨Х: ╤В╨╕╨║╨╛╨▓ ╨╜╨╡╤В ╤Г╨╢╨╡ {int(idle_sec // 60)} ╨╝╨╕╨╜ тАФ "
                          f"╨┐╤А╨╛╨▓╨╡╤А╤М ╤В╨╡╤А╨╝╨╕╨╜╨░╨╗ (╨╛╤В╨║╨╗╤О╤З╨╡╨╜╨╕╨╡/╤А╤Л╨╜╨╛╨║ ╨╖╨░╨║╤А╤Л╤В).", flush=True)
                    last_conn_warn_time = now
                time.sleep(60 if is_weekend else bt_cfg.poll_interval)  # ╨▓╤Л╤Е╨╛╨┤╨╜╨╛╨╣ тАФ ╤В╨╕╨║╨╛╨▓ ╨╜╨╡╤В, ╤А╨╡╨╢╨╡
                continue
            last_ticks_time = now

            # ╨Ю╨▒╨╜╨╛╨▓╨╗╨╡╨╜╨╕╨╡ ╨▒╨░╤А╨╛╨▓
            any_finalized = False
            for sym in ticks:
                if not is_weekend and sym in symbol_data:  # ╨▒╤Г╨┤╨╜╨╕ тАФ ╨╛╨▒╨╜╨╛╨▓╨╗╤П╨╡╨╝ ╨▒╨░╤А╤Л; ╨▓╤Л╤Е╨╛╨┤╨╜╨╛╨╣ тАФ ╨╜╨╡ ╨╛╨▒╨╜╨╛╨▓╨╗╤П╨╡╨╝
                    bid, ask = ticks[sym]
                    try:
                        if update_symbol_bar(sym, bid, ask, now):
                            any_finalized = True
                    except Exception as e:
                        print(f"\n[WARN] ╨Ю╤И╨╕╨▒╨║╨░ ╨╛╨▒╨╜╨╛╨▓╨╗╨╡╨╜╨╕╤П ╨▒╨░╤А╨░ {sym}: {e!r}", flush=True)

            # ╨в╤А╨╡╨╣╨╗╨╕╨╜╨│-╤Б╤В╨╛╨┐ (ATR chandelier) тАФ ╨╜╨╡╨╖╨░╨▓╨╕╤Б╨╕╨╝╨╛ ╨╛╤В ╤Б╤В╤А╨░╤В╨╡╨│╨╕╨╣
            try:
                trail_mgr.update(symbol_data, ticks)
            except Exception as e:
                print(f"\n[WARN] ╨Ю╤И╨╕╨▒╨║╨░ ╤В╤А╨╡╨╣╨╗╨╕╨╜╨│-╤Б╤В╨╛╨┐╨░: {e!r}", flush=True)

            # ╨Я╤А╨╛╨▓╨╡╤А╨║╨░ ╤Б╨╕╨│╨╜╨░╨╗╨╛╨▓ тАФ ╨в╨Ю╨Ы╨м╨Ъ╨Ю ╨▓ ╨▒╤Г╨┤╨╜╨╕ (╨Я╨╜-╨Я╤В), ╤А╤Л╨╜╨╛╨║ ╨╖╨░╨║╤А╤Л╤В ╨б╨▒-╨Т╤Б
            if any_finalized and now.weekday() < 5:  # ╨Я╨╜=0 ... ╨Я╤В=4
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
                    print(f"\n[WARN] ╨Ю╤И╨╕╨▒╨║╨░ ╨┐╤А╨╛╨▓╨╡╤А╨║╨╕ ╤Б╨╕╨│╨╜╨░╨╗╨╛╨▓: {e!r}", flush=True)

            # ╨Ю╨▒╨╜╨╛╨▓╨╗╨╡╨╜╨╕╨╡ active_state.json ╨┐╤А╨╕╨╝╨╡╤А╨╜╨╛ ╤А╨░╨╖ ╨▓ ╨╝╨╕╨╜╤Г╤В╤Г
            if (now - last_state_write).total_seconds() >= 60:
                write_active_state(active, active_strategies, balance, risk_cfg.max_risk_pct, JOURNAL_DIR)



                last_state_write = now

            # ╨б╨╝╨╡╨╜╨░ ╨╝╨╡╤Б╤П╤Ж╨░ тЖТ ╨╜╨╛╨▓╤Л╨╣ ╤Д╨░╨╣╨╗ ╨╢╤Г╤А╨╜╨░╨╗╨░
            if now.strftime('%Y%m') != journal_month:
                save_journal(journal_df, JOURNAL_FILE)
                journal_month = now.strftime('%Y%m')
                JOURNAL_FILE = os.path.join(JOURNAL_DIR, f"journal_{journal_month}.csv")
                journal_df = load_journal(JOURNAL_FILE, COLUMNS)
                print(f"\n[{now}] ╨Э╨╛╨▓╤Л╨╣ ╨╢╤Г╤А╨╜╨░╨╗: {JOURNAL_FILE}", flush=True)

            # ╨Я╨╡╤А╨╕╨╛╨┤╨╕╤З╨╡╤Б╨║╨╛╨╡ ╤Б╨╛╤Е╤А╨░╨╜╨╡╨╜╨╕╨╡ ╨╢╤Г╤А╨╜╨░╨╗╨░
            if (now - last_journal_write).total_seconds() >= bt_cfg.journal_save_every_sec:
                save_journal(journal_df, JOURNAL_FILE)
                last_journal_write = now

            # ╨б╤В╨░╤В╤Г╤Б тАФ ╨║╨╛╨╝╨┐╨░╨║╤В╨╜╨░╤П ╨░╨│╤А╨╡╨│╨╕╤А╨╛╨▓╨░╨╜╨╜╨░╤П ╤Б╤В╨░╤В╨╕╤Б╤В╨╕╨║╨░
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

            status_str = ' | '.join(sym_stats) if sym_stats else '╨╜╨╡╤В ╨░╨║╤В╨╕╨▓╨╜╤Л╤Е'
            # print(f"\r[{now.strftime('%H:%M:%S')}] ╨▒╨░╤А {bar_time} | "
            #       f"╨░╨║╤В╨╕╨▓╨╜╤Л╤Е {len(active_strategies)} | ╨┐╨╛╨╖╨╕╤Ж╨╕╨╣ {active_pos} | "
            #       f"{status_str} | ╨╢╨┤╤С╨╝...", end='', flush=True)

            time.sleep(60 if is_weekend else bt_cfg.poll_interval)  # ╨▓╤Л╤Е╨╛╨┤╨╜╨╛╨╣ тАФ ╤В╨╕╨║╨╛╨▓ ╨╜╨╡╤В, ╤А╨╡╨╢╨╡

    except KeyboardInterrupt:
        print("\n╨Ю╤Б╤В╨░╨╜╨╛╨▓╨║╨░ ╨┐╨╛ Ctrl+F2...")

    except Exception as exc:
        print(f"\n[╨Ъ╨а╨Ш╨в╨Ш╨з╨Э╨Ю] ╨Р╨▓╨░╤А╨╕╨╣╨╜╨░╤П ╨╛╤Б╤В╨░╨╜╨╛╨▓╨║╨░: {exc!r}", flush=True)
        raise

    finally:
        save_journal(journal_df, JOURNAL_FILE)
        write_active_state(active, active_strategies, balance, risk_cfg.max_risk_pct, JOURNAL_DIR)



        try:
            mt5.shutdown()
        except Exception:
            pass



        print("╨Ц╤Г╤А╨╜╨░╨╗ ╨╕ ╤Б╨╛╤Б╤В╨╛╤П╨╜╨╕╨╡ ╤Б╨╛╤Е╤А╨░╨╜╨╡╨╜╤Л. ╨в╨╡╤А╨╝╨╕╨╜╨░╨╗ ╨╛╤В╨║╨╗╤О╤З╤С╨╜.")
