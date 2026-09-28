import MetaTrader5 as mt5
from datetime import datetime, timedelta, date
import os
import csv
import time
import socket
import warnings
warnings.filterwarnings('ignore')

from functions import terminal_on, run_full_backtest
from daily_report import generate_daily_report, generate_missing_reports
from risk_manager import calc_metrics, composite_score, distribute_lots, check_integration_budget, MAX_COMBOS_PER_STRATEGY
from strategy_engine import (
    write_ranking, sync_active_strategies, check_active_signals,
    send_order, close_order, get_deal_exit_price,
    strategy_key, make_magic, _record_close,
    deduplicate_results, _short_name,
    write_active_state, get_non_usd
)

# ═══ ВЫЧИСЛИТЕЛЬНЫЙ БЮДЖЕТ ═══
# Максимальное число комбинаций на ОДИН символ (все стратегии вместе).
# Бэктест идёт по multiprocessing — каждый символ считает все комбинации.
# Если сумма всех стратегий превышает этот лимит — новые стратегии блокируются.
# ═══ ПАРАМЕТРЫ БЭКТЕСТА ═══
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
from data_loader import (
    symbol_data, load_h1, update_symbol_bar,
    load_journal, save_journal, record_trade,
)


# ═══ КОНФИГУРАЦИЯ ═══



SYMBOLS = ["EURUSDrfd", "GBPUSDrfd", "USDJPYrfd", "USDCHFrfd",
           "USDCADrfd", "AUDUSDrfd", "NZDUSDrfd"]
K_PERIOD_RANGE  = (7, 28, 7)
SL_POINTS_RANGE = (300, 1200, 400)
TP_POINTS_RANGE = (300, 1200, 400)
PARABOLIC_STEP_RANGE = (0.02, 0.2, 0.02)
PARABOLIC_MAX_RANGE  = (0.2, 0.4, 0.05)
MA_PERIOD_RANGE      = (10, 200, 25)

RF_LOOKBACK_RANGE = (200, 400, 100)
RF_NBARS_RANGE = (5, 10, 5)
RF_THRESHOLD_RANGE = (0.55, 0.65, 0.10)

LOGREG_LOOKBACK_RANGE = (200, 400, 100)
LOGREG_NBARS_RANGE = (6, 12, 6)
LOGREG_THRESHOLD_RANGE = (0.55, 0.65, 0.10)

# MACD Cross (только MACD crossover)
MACD_CROSS_FAST_RANGE   = (10, 14, 2)
MACD_CROSS_SLOW_RANGE   = (24, 28, 2)
MACD_CROSS_SIGNAL_RANGE = (7, 11, 2)

# RSI Reversal (только RSI)
RSI_REV_PERIOD_RANGE     = (12, 16, 2)
RSI_REV_OVERSOLD_RANGE   = (25, 35, 5)
RSI_REV_OVERBOUGHT_RANGE = (65, 75, 5)

# Bollinger
BB_PERIOD_RANGE = (15, 25, 5)
BB_STD_RANGE = (1.5, 2.5, 0.5)
VOLUME_PERIOD_RANGE = (15, 25, 5)

# EMA Crossover
EMA_FAST_RANGE = (8, 12, 1)
EMA_SLOW_RANGE = (18, 24, 3)

# RSI Divergence
RSI_DIV_PERIOD_RANGE = (12, 16, 2)
RSI_DIV_LOOKBACK_RANGE = (4, 7, 1)
RSI_DIV_THRESHOLD_RANGE = (0.4, 0.6, 0.1)

# Ichimoku
TENKAN_RANGE = (7, 12, 4)
KIJUN_RANGE = (22, 30, 4)
SENKOU_B_RANGE = (45, 55, 5)
DISPLACEMENT_RANGE = (22, 30, 4)

# Z-score reversion
ZSCORE_SMA_PERIOD_RANGE = (20, 50, 10)
ZSCORE_THRESHOLD_RANGE = (1.5, 2.5, 0.5)
ZSCORE_VOL_PERIOD_RANGE = (15, 25, 5)

# Autocorrelation momentum
AUTOCORR_LAG_RANGE = (1, 5, 2)
AUTOCORR_THRESHOLD_RANGE = (0.2, 0.4, 0.1)
AUTOCORR_VOL_PERIOD_RANGE = (15, 25, 5)

# Hurst regime filter
HURST_WINDOW_RANGE = (20, 60, 10)
HURST_TREND_THRESHOLD_RANGE = (0.5, 0.7, 0.1)
HURST_VOL_PERIOD_RANGE = (20, 50, 10)

# Linear Regression Channel
LRC_PERIOD_RANGE = (20, 50, 10)
LRC_STD_THRESHOLD_RANGE = (1.5, 2.5, 0.5)
LRC_VOL_PERIOD_RANGE = (15, 25, 5)

# Percentile reversion
PCT_PERIOD_RANGE = (20, 50, 10)
PCT_LOW_RANGE = (3, 8, 2)
PCT_HIGH_RANGE = (92, 97, 2)
PCT_VOL_PERIOD_RANGE = (15, 25, 5)

# Runs Test trend
RUNS_WINDOW_RANGE = (20, 50, 10)
RUNS_THRESHOLD_RANGE = (1.5, 2.0, 0.2)
RUNS_VOL_PERIOD_RANGE = (15, 25, 5)

# Cointegration pairs
COINT_WINDOW_RANGE = (20, 60, 10)
COINT_THRESHOLD_RANGE = (1.5, 2.5, 0.5)
COINT_BETA_PEROID_RANGE = (20, 50, 10)

# Rolling Sharpe filter
SHARPE_WINDOW_RANGE = (20, 60, 10)
SHARPE_THRESHOLD_RANGE = (0.3, 0.7, 0.1)
SHARPE_VOL_PERIOD_RANGE = (15, 25, 5)

# Skewness extreme
SKEW_WINDOW_RANGE = (20, 50, 10)
SKEW_THRESHOLD_RANGE = (0.8, 1.2, 0.2)
SKEW_VOL_PERIOD_RANGE = (15, 25, 5)

# Bayesian trend update
BAYES_WINDOW_RANGE = (20, 50, 10)
BAYES_THRESHOLD_RANGE = (0.6, 0.7, 0.05)
BAYES_PRIOR_RANGE = (0.4, 0.6, 0.1)

# Kurtosis spike
KURT_WINDOW_RANGE = (20, 60, 10)
KURT_THRESHOLD_RANGE = (3.0, 6.0, 1.0)
KURT_VOL_PERIOD_RANGE = (15, 25, 5)

# Chi-square distribution
CHISQ_WINDOW_RANGE = (20, 50, 10)
CHISQ_ENTRY_RANGE = (0.03, 0.07, 0.02)
CHISQ_EXIT_RANGE = (0.15, 0.25, 0.05)
CHISQ_VOL_PERIOD_RANGE = (15, 25, 5)

BACKTEST_DAYS = 30
POLL_INTERVAL = 5

MAX_RISK_PCT = 0.05
MIN_LOT = 0.01
MIN_SCORE = 1.0
NIGHT_BACKTEST_HOUR = 3
MAGIC_BASE = 770000

# ═══ РИСК-МЕНЕДЖМЕНТ ═══
# Лимиты позиций (пункт 3)
MAX_TOTAL_POSITIONS = 15        # Максимум позиций одновременно
MAX_POSITIONS_PER_SYMBOL = 3    # Максимум на один символ

# Daily stop-loss / equity stop (пункт 6)
DAILY_LOSS_LIMIT_PCT = 3.0      # Макс убыток за день в %
EQUITY_STOP_PCT = 10.0          # Глобальный стоп при просадке equity в %

# Real-time quota recalc (пункт 4)
REALTIME_QUOTA_RECALC = True    # Пересчёт квоты в реальном времени
QUOTA_RECALC_INTERVAL_SEC = 300 # Интервал пересчёта квоты (5 мин)

# Stops levels (пункт 5)
MIN_SL_DISTANCE_POINTS = 10     # Минимальное расстояние SL
MAX_SL_DISTANCE_POINTS = 500    # Максимальное расстояние SL

# Допустимое «молчание» терминала до предупреждения о потере связи
CONNECTION_TIMEOUT_SEC = 300      # тиков нет 5 минут — подозрительно (кроме выходных)
CONNECTION_WARN_EVERY_SEC = 600   # повторное предупреждение не чаще раза в 10 минут
JOURNAL_SAVE_EVERY_SEC = 300      # периодическое сохранение журнала (страховка от падения)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_DIR = os.path.join(BASE_DIR, "journals")
JOURNAL_FILE = os.path.join(JOURNAL_DIR, f"journal_{datetime.now().strftime('%Y%m')}.csv")

COLUMNS = ['symbol', 'param_key', 'sl_points', 'tp_points',
           'entry_time', 'exit_time', 'direction',
           'entry_price', 'exit_price', 'lot', 'profit',
           'exit_reason', 'ticket']


# ═══ УТИЛИТЫ ═══
def float_range(start, stop, step):
    """range() для float — включает граничное значение."""
    result = []
    v = start
    while v < stop - 1e-9:
        result.append(round(v, 4))
        v += step
    result.append(round(stop, 4))
    return result


def int_range(start, stop, step):
    """range() для int — включает граничное значение."""
    return list(range(start, stop, step)) + [stop]


K_PERIODS       = int_range(*K_PERIOD_RANGE)
SL_POINTS_LIST  = int_range(*SL_POINTS_RANGE)
TP_POINTS_LIST  = int_range(*TP_POINTS_RANGE)
PARABOLIC_STEPS = float_range(*PARABOLIC_STEP_RANGE)
PARABOLIC_MAXS  = float_range(*PARABOLIC_MAX_RANGE)
MA_PERIODS      = int_range(*MA_PERIOD_RANGE)
RF_LOOKBACKS    = int_range(*RF_LOOKBACK_RANGE)
RF_NBARS        = int_range(*RF_NBARS_RANGE)
RF_THRESHOLDS   = float_range(*RF_THRESHOLD_RANGE)
LOGREG_LOOKBACKS    = int_range(*LOGREG_LOOKBACK_RANGE)
LOGREG_NBARS        = int_range(*LOGREG_NBARS_RANGE)
LOGREG_THRESHOLDS   = float_range(*LOGREG_THRESHOLD_RANGE)

# Новые стратегии
MACD_CROSS_FAST_LIST      = int_range(*MACD_CROSS_FAST_RANGE)
MACD_CROSS_SLOW_LIST      = int_range(*MACD_CROSS_SLOW_RANGE)
MACD_CROSS_SIGNAL_LIST    = int_range(*MACD_CROSS_SIGNAL_RANGE)
RSI_REV_PERIOD_LIST       = int_range(*RSI_REV_PERIOD_RANGE)
RSI_REV_OVERSOLD_LIST     = int_range(*RSI_REV_OVERSOLD_RANGE)
RSI_REV_OVERBOUGHT_LIST   = int_range(*RSI_REV_OVERBOUGHT_RANGE)

BB_PERIOD_LIST      = int_range(*BB_PERIOD_RANGE)
BB_STD_LIST         = float_range(*BB_STD_RANGE)
VOLUME_PERIOD_LIST  = int_range(*VOLUME_PERIOD_RANGE)

EMA_FAST_LIST       = int_range(*EMA_FAST_RANGE)
EMA_SLOW_LIST       = int_range(*EMA_SLOW_RANGE)

RSI_DIV_PERIOD_LIST     = int_range(*RSI_DIV_PERIOD_RANGE)
RSI_DIV_LOOKBACK_LIST   = int_range(*RSI_DIV_LOOKBACK_RANGE)
RSI_DIV_THRESHOLD_LIST  = float_range(*RSI_DIV_THRESHOLD_RANGE)

TENKAN_LIST       = int_range(*TENKAN_RANGE)
KIJUN_LIST        = int_range(*KIJUN_RANGE)
SENKOU_B_LIST     = int_range(*SENKOU_B_RANGE)
DISPLACEMENT_LIST = int_range(*DISPLACEMENT_RANGE)

# STANDALONE стратегии
ZSCORE_SMA_PERIOD_LIST  = int_range(*ZSCORE_SMA_PERIOD_RANGE)
ZSCORE_THRESHOLD_LIST   = float_range(*ZSCORE_THRESHOLD_RANGE)
ZSCORE_VOL_PERIOD_LIST  = int_range(*ZSCORE_VOL_PERIOD_RANGE)

AUTOCORR_LAG_LIST       = int_range(*AUTOCORR_LAG_RANGE)
AUTOCORR_THRESHOLD_LIST = float_range(*AUTOCORR_THRESHOLD_RANGE)
AUTOCORR_VOL_PERIOD_LIST = int_range(*AUTOCORR_VOL_PERIOD_RANGE)

HURST_WINDOW_LIST       = int_range(*HURST_WINDOW_RANGE)
HURST_TREND_THRESHOLD_LIST = float_range(*HURST_TREND_THRESHOLD_RANGE)
HURST_VOL_PERIOD_LIST   = int_range(*HURST_VOL_PERIOD_RANGE)

LRC_PERIOD_LIST         = int_range(*LRC_PERIOD_RANGE)
LRC_STD_THRESHOLD_LIST  = float_range(*LRC_STD_THRESHOLD_RANGE)
LRC_VOL_PERIOD_LIST     = int_range(*LRC_VOL_PERIOD_RANGE)

PCT_PERIOD_LIST         = int_range(*PCT_PERIOD_RANGE)
PCT_LOW_LIST            = int_range(*PCT_LOW_RANGE)
PCT_HIGH_LIST           = int_range(*PCT_HIGH_RANGE)
PCT_VOL_PERIOD_LIST     = int_range(*PCT_VOL_PERIOD_RANGE)

RUNS_WINDOW_LIST        = int_range(*RUNS_WINDOW_RANGE)
RUNS_THRESHOLD_LIST     = float_range(*RUNS_THRESHOLD_RANGE)
RUNS_VOL_PERIOD_LIST    = int_range(*RUNS_VOL_PERIOD_RANGE)

COINT_WINDOW_LIST       = int_range(*COINT_WINDOW_RANGE)
COINT_THRESHOLD_LIST    = float_range(*COINT_THRESHOLD_RANGE)
COINT_BETA_PERIOD_LIST  = int_range(*COINT_BETA_PEROID_RANGE)

SHARPE_WINDOW_LIST      = int_range(*SHARPE_WINDOW_RANGE)
SHARPE_THRESHOLD_LIST   = float_range(*SHARPE_THRESHOLD_RANGE)
SHARPE_VOL_PERIOD_LIST  = int_range(*SHARPE_VOL_PERIOD_RANGE)

SKEW_WINDOW_LIST        = int_range(*SKEW_WINDOW_RANGE)
SKEW_THRESHOLD_LIST     = float_range(*SKEW_THRESHOLD_RANGE)
SKEW_VOL_PERIOD_LIST    = int_range(*SKEW_VOL_PERIOD_RANGE)

BAYES_WINDOW_LIST       = int_range(*BAYES_WINDOW_RANGE)
BAYES_THRESHOLD_LIST    = float_range(*BAYES_THRESHOLD_RANGE)
BAYES_PRIOR_LIST        = float_range(*BAYES_PRIOR_RANGE)

KURT_WINDOW_LIST        = int_range(*KURT_WINDOW_RANGE)
KURT_THRESHOLD_LIST     = float_range(*KURT_THRESHOLD_RANGE)
KURT_VOL_PERIOD_LIST    = int_range(*KURT_VOL_PERIOD_RANGE)

CHISQ_WINDOW_LIST       = int_range(*CHISQ_WINDOW_RANGE)
CHISQ_ENTRY_LIST        = float_range(*CHISQ_ENTRY_RANGE)
CHISQ_EXIT_LIST         = float_range(*CHISQ_EXIT_RANGE)
CHISQ_VOL_PERIOD_LIST   = int_range(*CHISQ_VOL_PERIOD_RANGE)

# ═══ ВЫЧИСЛИТЕЛЬНЫЙ БЮДЖЕТ ═══
def _combo(*args):
    """Произведение длин списков."""
    result = 1
    for a in args:
        result *= a
    return result

# Считаем комбинации для каждой стратегии
integration_budgets_dict = {
    'Stoch':          _combo(len(K_PERIODS), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'Parabolic':      _combo(len(PARABOLIC_STEPS), len(PARABOLIC_MAXS), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'MA':             _combo(len(MA_PERIODS), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'RandomForest':   _combo(len(RF_LOOKBACKS), len(RF_NBARS), len(RF_THRESHOLDS), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'LogReg':         _combo(len(LOGREG_LOOKBACKS), len(LOGREG_NBARS), len(LOGREG_THRESHOLDS), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'MACD-Cross':     _combo(len(MACD_CROSS_FAST_LIST), len(MACD_CROSS_SLOW_LIST), len(MACD_CROSS_SIGNAL_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'RSI-Rev':        _combo(len(RSI_REV_PERIOD_LIST), len(RSI_REV_OVERSOLD_LIST), len(RSI_REV_OVERBOUGHT_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'Bollinger':      _combo(len(BB_PERIOD_LIST), len(BB_STD_LIST), len(VOLUME_PERIOD_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'EMA':            _combo(len(EMA_FAST_LIST), len(EMA_SLOW_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'RSI-Div':        _combo(len(RSI_DIV_PERIOD_LIST), len(RSI_DIV_LOOKBACK_LIST), len(RSI_DIV_THRESHOLD_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'Ichimoku':       _combo(len(TENKAN_LIST), len(KIJUN_LIST), len(SENKOU_B_LIST), len(DISPLACEMENT_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'Zscore':         _combo(len(ZSCORE_SMA_PERIOD_LIST), len(ZSCORE_THRESHOLD_LIST), len(ZSCORE_VOL_PERIOD_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'Autocorr':       _combo(len(AUTOCORR_LAG_LIST), len(AUTOCORR_THRESHOLD_LIST), len(AUTOCORR_VOL_PERIOD_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'Hurst':          _combo(len(HURST_WINDOW_LIST), len(HURST_TREND_THRESHOLD_LIST), len(HURST_VOL_PERIOD_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'LRC':            _combo(len(LRC_PERIOD_LIST), len(LRC_STD_THRESHOLD_LIST), len(LRC_VOL_PERIOD_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'Percentile':     _combo(len(PCT_PERIOD_LIST), len(PCT_LOW_LIST), len(PCT_HIGH_LIST), len(PCT_VOL_PERIOD_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'Runs':           _combo(len(RUNS_WINDOW_LIST), len(RUNS_THRESHOLD_LIST), len(RUNS_VOL_PERIOD_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'Coint':          _combo(len(COINT_WINDOW_LIST), len(COINT_THRESHOLD_LIST), len(COINT_BETA_PERIOD_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'Sharpe':         _combo(len(SHARPE_WINDOW_LIST), len(SHARPE_THRESHOLD_LIST), len(SHARPE_VOL_PERIOD_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'Skewness':       _combo(len(SKEW_WINDOW_LIST), len(SKEW_THRESHOLD_LIST), len(SKEW_VOL_PERIOD_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'Bayesian':       _combo(len(BAYES_WINDOW_LIST), len(BAYES_THRESHOLD_LIST), len(BAYES_PRIOR_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'Kurtosis':       _combo(len(KURT_WINDOW_LIST), len(KURT_THRESHOLD_LIST), len(KURT_VOL_PERIOD_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
    'ChiSq':          _combo(len(CHISQ_WINDOW_LIST), len(CHISQ_ENTRY_LIST), len(CHISQ_EXIT_LIST), len(CHISQ_VOL_PERIOD_LIST), len(SL_POINTS_LIST), len(TP_POINTS_LIST)),
}


if __name__ == '__main__':
    # ═══ ВЫЧИСЛИТЕЛЬНЫЙ БЮДЖЕТ ═══
    budget_results = check_integration_budget(integration_budgets_dict, SYMBOLS)

    print("Боевой режим: все стратегии, полный перебор")

    # ═══ ПОДКЛЮЧЕНИЕ ═══
    terminal_on('demo')
    os.makedirs(JOURNAL_DIR, exist_ok=True)

    # ═══ ЗАГРУЗКА ИСТОРИИ ═══
    print("Загрузка истории...")
    for sym in SYMBOLS:
        h1 = load_h1(sym)
        if h1 is not None:
            mt5.symbol_select(sym, True)
            info = mt5.symbol_info(sym)
            symbol_data[sym] = {
                'df_h1': h1,
                'current_hour': (h1.index[-1] + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0),
                'forming_bar': None,
                'info': info,
            }
            print(f"  {sym}: {len(h1)} баров H1")
        else:
            print(f"  {sym}: нет данных")

    # ═══ ЖУРНАЛ ═══
    journal_df = load_journal(JOURNAL_FILE, COLUMNS)


    # ═══ АКТИВНЫЕ СТРАТЕГИИ ═══
    active_strategies = {}

    # ═══ ГЕНЕРАЦИЯ ПРОПУЩЕННЫХ ОТЧЁТОВ ═══
    print("\nПроверка пропущенных daily отчётов...")
    # Ищем первый день с реестром и генерируем всё до вчера
    registry_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'journals', 'strategy_registry.csv')
    if os.path.exists(registry_path):
        # Берём дату первой записи из реестра
        with open(registry_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if rows:
                first_date_str = rows[0].get('activated_at', '')
                if first_date_str:
                    first_date = datetime.strptime(first_date_str, '%Y-%m-%dT%H:%M:%S.%f').date()
                    yesterday = date.today() - timedelta(days=1)
                    if first_date <= yesterday:
                        generate_missing_reports(first_date, yesterday)
    else:
        print("  ⚠️  Реестр не найден — отчёты будут генерироваться с первого дня")


    # ═══ ПЕРВЫЙ РАСЧЁТ ═══
    print("\nБэктест (первый расчёт)...")

    # force_recalc=True — игнорирует чекпоинты и пересчитывает всё с нуля
    FORCE_RECALC = False

    all_top, all_results = run_full_backtest(
        SYMBOLS, symbol_data, K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST,
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
        BACKTEST_DAYS, 9999,
        test_strategy=None,
        test_mode=False,
        force_recalc=FORCE_RECALC
    )

    acc = mt5.account_info()
    balance = acc.balance if acc else 1_000_000
    if acc is not None:
        mode_name = {0: 'demo', 1: 'contest', 2: 'real'}.get(acc.trade_mode, str(acc.trade_mode))
        print(f"Счёт: {acc.login} | Сервер: {acc.server} | Валюта: {acc.currency} | Режим: {mode_name}")
    print(f"Баланс: {balance:.0f} руб | Квота риска: {balance * MAX_RISK_PCT:.0f} руб | Порог score >= {MIN_SCORE}")


    # deduplicate_results уже вызвана внутри run_full_backtest
    deduped_results = all_results
    print(f"После дедупликации: {len(deduped_results)} комбинаций")

    active = distribute_lots(deduped_results, symbol_data, balance,
                             MAX_RISK_PCT, MIN_LOT, MIN_SCORE)


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

    write_ranking(active, all_results, JOURNAL_DIR, BACKTEST_DAYS, len(active), None)

    sync_active_strategies(active, datetime.now(), symbol_data, active_strategies,
                           close_order, get_deal_exit_price, record_trade,
                           strategy_key, make_magic, MAGIC_BASE, len(active))

    write_active_state(active, active_strategies, balance, MAX_RISK_PCT, JOURNAL_DIR)

    print(f"\nЗапуск цикла. Ctrl+C для остановки.\n")


    # ═══ ГЛАВНЫЙ ЦИКЛ ═══
    # Стартовый бэктест выше считается «сегодняшним» — ночной перерасчёт начнётся с 3:00.
    last_full_backtest_date = datetime.now().date()
    last_mode_check = datetime.now().date()
    last_state_write = datetime.now()
    last_journal_write = datetime.now()
    journal_month = datetime.now().strftime('%Y%m')
    last_ticks_time = datetime.now()
    last_conn_warn_time = datetime.min
    last_balance_refresh = datetime.now()
    last_quota_recalc = datetime.now()
    initial_equity = None  # Для equity stop (пункт 6)
    daily_start_balance = None  # Для daily stop-loss (пункт 6)

    try:
        while True:
            now = datetime.now()

            # Смена дня
            if now.date() != last_mode_check:
                last_mode_check = now.date()
                print(f"\n[{now}] Новый день")

            # Ночной перерасчёт: один раз в сутки, начиная с 3:00.
            # Если машина спала в 3:00 — пересчёт выполнится при первом проходе после 3:00.
            if now.hour >= NIGHT_BACKTEST_HOUR and now.date() != last_full_backtest_date:
                last_full_backtest_date = now.date()
                print(f"\n[{now.strftime('%H:%M:%S')}] Ночной перерасчёт...")

                _, all_results = run_full_backtest(
                    SYMBOLS, symbol_data, K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST,
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
                    BACKTEST_DAYS, 9999,
                    test_strategy=None,
                    test_mode=False,
                    force_recalc=FORCE_RECALC
                )

                # Обновляем баланс перед ночным перерасчётом
                acc = mt5.account_info()
                balance = acc.balance if acc else 1_000_000
                # deduplicate_results уже вызвана внутри run_full_backtest
                deduped_results = all_results
                active = distribute_lots(deduped_results, symbol_data, balance,
                                         MAX_RISK_PCT, MIN_LOT, MIN_SCORE)
                print(f"Баланс: {balance:.0f} руб | Квота: {balance * MAX_RISK_PCT:.0f} руб | "
                      f"Активировано {len(active)} из {len(deduped_results)} (всего {len(all_results)})")

                write_ranking(active, all_results, JOURNAL_DIR, BACKTEST_DAYS, len(active), None)
                sync_active_strategies(active, now, symbol_data, active_strategies,
                                       close_order, get_deal_exit_price, record_trade,
                                       strategy_key, make_magic, MAGIC_BASE, len(active))
                write_active_state(active, active_strategies, balance, MAX_RISK_PCT, JOURNAL_DIR)
                
                # ── Генерация daily report за предыдущие сутки ──
                yesterday = now.date() - timedelta(days=1)
                report = generate_daily_report(yesterday)
                
                print(f"  Готово: {len(all_results)} комбинаций, {len(active)} активных")

            # Периодическое обновление баланса (раз в минуту)
            if (now - last_balance_refresh).total_seconds() >= 60:
                acc = mt5.account_info()
                if acc is not None:
                    balance = acc.balance
                    equity = acc.equity
                    
                    # Инициализация initial_equity при старте
                    if initial_equity is None:
                        initial_equity = equity
                        print(f"  [INIT] Initial equity: {equity:.2f}")
                    
                    # Сброс daily_start_balance в начале нового дня
                    if daily_start_balance is None or now.date() != last_mode_check:
                        daily_start_balance = balance
                        print(f"  [INIT] Daily start balance: {balance:.2f}")
                    
                    last_balance_refresh = now
                    
                    # ── Проверка 1: Daily stop-loss (пункт 6) ──
                    if daily_start_balance is not None:
                        from risk_manager import check_daily_loss_limit
                        dl_ok, dl_pct, dl_reason = check_daily_loss_limit(
                            daily_start_balance, equity, DAILY_LOSS_LIMIT_PCT
                        )
                        if not dl_ok:
                            print(f"\n  [STOP] Daily loss limit: {dl_reason} — остановка торговли!")
                            # Закрываем все позиции
                            for key, s in list(active_strategies.items()):
                                if s['position'] is not None:
                                    print(f"  -> Закрытие {key} по daily stop-loss")
                                    exit_price = close_order(s['symbol'], s['position']['ticket'],
                                                            s['position']['direction'], s['magic'], symbol_data)
                                    if exit_price is not None:
                                        _record_close(key, s, now, exit_price, 'daily_stop', symbol_data,
                                                     record_trade, journal_df, JOURNAL_FILE)
                            continue
                    
                    # ── Проверка 2: Equity stop (пункт 6) ──
                    if initial_equity is not None:
                        from risk_manager import check_equity_stop
                        eq_ok, eq_dd, eq_reason = check_equity_stop(equity, initial_equity, EQUITY_STOP_PCT)
                        if not eq_ok:
                            print(f"\n  [STOP] Equity stop: {eq_reason} — аварийная остановка!")
                            # Закрываем все позиции и выходим
                            for key, s in list(active_strategies.items()):
                                if s['position'] is not None:
                                    print(f"  -> Закрытие {key} по equity stop")
                                    exit_price = close_order(s['symbol'], s['position']['ticket'],
                                                            s['position']['direction'], s['magic'], symbol_data)
                                    if exit_price is not None:
                                        _record_close(key, s, now, exit_price, 'equity_stop', symbol_data,
                                                     record_trade, journal_df, JOURNAL_FILE)
                            raise RuntimeError(f"Equity stop triggered: {eq_reason}")
                    
                    # ── Проверка 3: Realtime quota recalc (пункт 4) ──
                    if REALTIME_QUOTA_RECALC and (now - last_quota_recalc).total_seconds() >= QUOTA_RECALC_INTERVAL_SEC:
                        from risk_manager import realtime_quota_recalc
                        active_positions = []
                        for s in active_strategies.values():
                            if s['position'] is not None:
                                active_positions.append({
                                    'symbol': s['symbol'],
                                    'lot': s['position']['lot'],
                                    'sl_points': s['sl_points']
                                })
                        quota_ok, risk_pct, quota = realtime_quota_recalc(balance, active_positions, MAX_RISK_PCT)
                        if not quota_ok:
                            print(f"  [WARN] Realtime quota exceeded: risk={risk_pct:.2f}% > quota — "
                                  f"новые ордера не открываются до пересчёта в 3:00")

            # Тики
            ticks = {}
            for sym in SYMBOLS:
                try:
                    t = mt5.symbol_info_tick(sym)
                    if t is not None:
                        ticks[sym] = (t.bid, t.ask)
                except Exception as e:
                    print(f"\n[WARN] Ошибка получения тика {sym}: {e!r}", flush=True)

            if not ticks:
                idle_sec = (now - last_ticks_time).total_seconds()
                if (idle_sec >= CONNECTION_TIMEOUT_SEC
                        and (now - last_conn_warn_time).total_seconds() >= CONNECTION_WARN_EVERY_SEC):
                    print(f"\n[{now}] ВНИМАНИЕ: тиков нет уже {int(idle_sec // 60)} мин — "
                          f"проверь терминал (отключение/рынок закрыт).", flush=True)
                    last_conn_warn_time = now
                time.sleep(POLL_INTERVAL)
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

            # Проверка сигналов
            if any_finalized:
                try:
                    # Формируем risk_params для send_order
                    risk_params = {
                        'check_margin': True,
                        'check_stops': True,
                        'min_sl_distance_points': MIN_SL_DISTANCE_POINTS,
                        'max_sl_distance_points': MAX_SL_DISTANCE_POINTS
                    }
                    
                    # Формируем position_limits
                    position_limits = {
                        'max_total': MAX_TOTAL_POSITIONS,
                        'max_per_symbol': MAX_POSITIONS_PER_SYMBOL
                    }
                    
                    check_active_signals(
                        now, active_strategies, symbol_data,
                        calc_stochastic, check_exit_stoch, check_entry_stoch,
                        calc_parabolic, check_exit_parabolic, check_entry_parabolic,
                        calc_moving_average, check_exit_ma, check_entry_ma,
                        send_order, close_order, get_deal_exit_price,
                        _record_close, MIN_LOT, record_trade,
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
                        risk_params=risk_params,
                        position_limits=position_limits,
                    )
                except Exception as e:
                    print(f"\n[WARN] Ошибка проверки сигналов: {e!r}", flush=True)

            # Обновление active_state.json примерно раз в минуту
            if (now - last_state_write).total_seconds() >= 60:
                write_active_state(active, active_strategies, balance, MAX_RISK_PCT, JOURNAL_DIR)
                last_state_write = now

            # Смена месяца → новый файл журнала
            if now.strftime('%Y%m') != journal_month:
                save_journal(journal_df, JOURNAL_FILE)
                journal_month = now.strftime('%Y%m')
                JOURNAL_FILE = os.path.join(JOURNAL_DIR, f"journal_{journal_month}.csv")
                journal_df = load_journal(JOURNAL_FILE, COLUMNS)
                print(f"\n[{now}] Новый журнал: {JOURNAL_FILE}", flush=True)

            # Периодическое сохранение журнала — страховка на случай падения процесса
            if (now - last_journal_write).total_seconds() >= JOURNAL_SAVE_EVERY_SEC:
                save_journal(journal_df, JOURNAL_FILE)
                last_journal_write = now

            # Статус — компактная агрегированная статистика
            active_pos = sum(1 for s in active_strategies.values() if s['position'] is not None)
            bar_time = '??'
            if SYMBOLS and SYMBOLS[0] in symbol_data:
                bar_time = symbol_data[SYMBOLS[0]]['current_hour'].strftime('%H:%M')
            
            # Агрегация: символ -> тип -> количество стратегий
            from collections import defaultdict
            stats = defaultdict(lambda: defaultdict(int))
            for key, s in active_strategies.items():
                sym = s['symbol']
                stype = s.get('type', 'stoch')
                stats[sym][stype] += 1
            
            # Формирование компактной строки
            sym_stats = []
            for sym in SYMBOLS:
                if sym in stats:
                    type_counts = [f"{t[0].upper()}({c})" for t, c in sorted(stats[sym].items())]
                    sym_stats.append(f"{get_non_usd(sym)}:{','.join(type_counts)}")
            
            status_str = ' | '.join(sym_stats) if sym_stats else 'нет активных'
            print(f"\r[{now.strftime('%H:%M:%S')}] бар {bar_time} | "
                  f"активных {len(active_strategies)} | позиций {active_pos} | "
                  f"{status_str} | ждём...", end='', flush=True)

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nОстановка по Ctrl+C...")

    except Exception as exc:
        print(f"\n[КРИТИЧНО] Аварийная остановка: {exc!r}", flush=True)
        raise

    finally:
        save_journal(journal_df, JOURNAL_FILE)
        write_active_state(active, active_strategies, balance, MAX_RISK_PCT, JOURNAL_DIR)
        try:
            mt5.shutdown()
        except Exception:
            pass
        print("Журнал и состояние сохранены. Терминал отключён.")
