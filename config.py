"""config.py — централизованная конфигурация StrategyCloud.

DataClass-контейнеры заменяют десятки глобальных переменных main.py
и 36+ позиционных аргументов run_full_backtest / _backtest_symbol /
check_active_signals. Единая точка для добавления новых стратегий.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple


# ═══════════════ УТИЛИТЫ ДИАПАЗОНОВ ═══════════════
def float_range(start, stop, step):
    """range() для float — включает граничное значение. Возвращает tuple."""
    result = []
    v = start
    while v < stop - 1e-9:
        result.append(round(v, 4))
        v += step
    result.append(round(stop, 4))
    return tuple(result)


def int_range(start, stop, step):
    """range() для int — включает граничное значение. Возвращает tuple."""
    return tuple(list(range(start, stop, step)) + [stop])


# ═══════════════ RANGE-СПЕКИ (источник значений) ═══════════════
SYMBOLS = ("EURUSDrfd", "GBPUSDrfd", "USDJPYrfd", "USDCHFrfd",
           "USDCADrfd", "AUDUSDrfd", "NZDUSDrfd")

K_PERIOD_RANGE = (7, 28, 7)
SL_POINTS_RANGE = (300, 1200, 400)
TP_POINTS_RANGE = (300, 1200, 400)
PARABOLIC_STEP_RANGE = (0.02, 0.2, 0.02)
PARABOLIC_MAX_RANGE = (0.2, 0.4, 0.05)
MA_PERIOD_RANGE = (10, 200, 25)

RF_LOOKBACK_RANGE = (200, 400, 100)
RF_NBARS_RANGE = (5, 10, 5)
RF_THRESHOLD_RANGE = (0.55, 0.65, 0.10)

LOGREG_LOOKBACK_RANGE = (200, 400, 100)
LOGREG_NBARS_RANGE = (6, 12, 6)
LOGREG_THRESHOLD_RANGE = (0.55, 0.65, 0.10)

# MACD Cross (только MACD crossover)
MACD_CROSS_FAST_RANGE = (10, 14, 2)
MACD_CROSS_SLOW_RANGE = (24, 28, 2)
MACD_CROSS_SIGNAL_RANGE = (7, 11, 2)

# RSI Reversal (только RSI)
RSI_REV_PERIOD_RANGE = (12, 16, 2)
RSI_REV_OVERSOLD_RANGE = (25, 35, 5)
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

# VWAP Reversion
VWAP_VOL_PERIOD_RANGE = (15, 25, 5)
VWAP_STD_MULT_RANGE = (1.5, 2.5, 0.5)

# Momentum Breakout
MOMENTUM_PERIOD_RANGE = (15, 25, 5)
MOMENTUM_THRESHOLD_RANGE = (0.03, 0.07, 0.01)

# Pin Bar Reversal
PIN_BAR_BODY_RATIO_RANGE = (0.2, 0.4, 0.1)

# Prev Daily Candle Direction
PREV_DAILY_HOLD_BARS_RANGE = (6, 18, 6)

# Rolling Correlation Momentum
CORR_WINDOW_RANGE = (15, 25, 5)
CORR_THRESHOLD_RANGE = (0.3, 0.7, 0.1)


# ═══════════════ DATACLASS-КОНТЕЙНЕРЫ ═══════════════
@dataclass(frozen=True)
class StrategyParams:
    """Все параметры стратегий (готовые кортежи значений для перебора)."""
    # Stochastic
    k_periods: Tuple[int, ...]
    sl_points_list: Tuple[int, ...]
    tp_points_list: Tuple[int, ...]
    # Parabolic
    parabolic_steps: Tuple[float, ...]
    parabolic_maxs: Tuple[float, ...]
    # Moving Average
    ma_periods: Tuple[int, ...]
    # Random Forest
    rf_lookbacks: Tuple[int, ...]
    rf_nbars: Tuple[int, ...]
    rf_thresholds: Tuple[float, ...]
    # Logistic Regression
    logreg_lookbacks: Tuple[int, ...]
    logreg_nbars: Tuple[int, ...]
    logreg_thresholds: Tuple[float, ...]
    # MACD Cross
    macd_cross_fast_list: Tuple[int, ...]
    macd_cross_slow_list: Tuple[int, ...]
    macd_cross_signal_list: Tuple[int, ...]
    # RSI Reversal
    rsi_rev_period_list: Tuple[int, ...]
    rsi_rev_oversold_list: Tuple[int, ...]
    rsi_rev_overbought_list: Tuple[int, ...]
    # Bollinger
    bb_period_list: Tuple[int, ...]
    bb_std_list: Tuple[float, ...]
    volume_period_list: Tuple[int, ...]
    # EMA Crossover
    ema_fast_list: Tuple[int, ...]
    ema_slow_list: Tuple[int, ...]
    # RSI Divergence
    rsi_div_period_list: Tuple[int, ...]
    rsi_div_lookback_list: Tuple[int, ...]
    rsi_div_threshold_list: Tuple[float, ...]
    # Ichimoku
    tenkan_list: Tuple[int, ...]
    kijun_list: Tuple[int, ...]
    senkou_b_list: Tuple[int, ...]
    displacement_list: Tuple[int, ...]
    # Z-score
    zscore_sma_period_list: Tuple[int, ...]
    zscore_threshold_list: Tuple[float, ...]
    zscore_vol_period_list: Tuple[int, ...]
    # Autocorrelation
    autocorr_lag_list: Tuple[int, ...]
    autocorr_threshold_list: Tuple[float, ...]
    autocorr_vol_period_list: Tuple[int, ...]
    # Hurst
    hurst_window_list: Tuple[int, ...]
    hurst_trend_threshold_list: Tuple[float, ...]
    hurst_vol_period_list: Tuple[int, ...]
    # Linear Regression Channel
    lrc_period_list: Tuple[int, ...]
    lrc_std_threshold_list: Tuple[float, ...]
    lrc_vol_period_list: Tuple[int, ...]
    # Percentile
    pct_period_list: Tuple[int, ...]
    pct_low_list: Tuple[int, ...]
    pct_high_list: Tuple[int, ...]
    pct_vol_period_list: Tuple[int, ...]
    # Runs Test
    runs_window_list: Tuple[int, ...]
    runs_threshold_list: Tuple[float, ...]
    runs_vol_period_list: Tuple[int, ...]
    # Cointegration
    coint_window_list: Tuple[int, ...]
    coint_threshold_list: Tuple[float, ...]
    coint_beta_period_list: Tuple[int, ...]
    # Rolling Sharpe
    sharpe_window_list: Tuple[int, ...]
    sharpe_threshold_list: Tuple[float, ...]
    sharpe_vol_period_list: Tuple[int, ...]
    # Skewness
    skew_window_list: Tuple[int, ...]
    skew_threshold_list: Tuple[float, ...]
    skew_vol_period_list: Tuple[int, ...]
    # Bayesian
    bayes_window_list: Tuple[int, ...]
    bayes_threshold_list: Tuple[float, ...]
    bayes_prior_list: Tuple[float, ...]
    # Kurtosis
    kurt_window_list: Tuple[int, ...]
    kurt_threshold_list: Tuple[float, ...]
    kurt_vol_period_list: Tuple[int, ...]
    # Chi-square
    chisq_window_list: Tuple[int, ...]
    chisq_entry_list: Tuple[float, ...]
    chisq_exit_list: Tuple[float, ...]
    chisq_vol_period_list: Tuple[int, ...]
    # VWAP Reversion
    vwap_vol_period_list: Tuple[int, ...]
    vwap_std_mult_list: Tuple[float, ...]
    # Momentum Breakout
    momentum_period_list: Tuple[int, ...]
    momentum_threshold_list: Tuple[float, ...]
    # Pin Bar Reversal
    pin_bar_body_ratio_list: Tuple[float, ...]
    # Prev Daily Candle Direction
    prev_daily_hold_bars_list: Tuple[int, ...]
    # Rolling Correlation Momentum
    corr_window_list: Tuple[int, ...]
    corr_threshold_list: Tuple[float, ...]


@dataclass(frozen=True)
class RiskParams:
    """Параметры риск-менеджмента."""
    max_total_positions: int = 999999   # ВРЕМЕННО отключено (было 15) — вернуть после проверки
    max_per_symbol: int = 999999  # ВРЕМЕННО отключено (было 3) — позиции по пропорции квоты
    daily_loss_limit_pct: float = 3.0
    equity_stop_pct: float = 10.0
    realtime_quota_recalc: bool = True
    quota_recalc_interval_sec: int = 300
    min_sl_distance_points: int = 10
    max_sl_distance_points: int = 5000
    max_risk_pct: float = 0.2
    min_lot: float = 0.01
    min_score: float = 1.0


@dataclass(frozen=True)
class BacktestConfig:
    """Конфигурация бэктеста и демона."""
    symbols: Tuple[str, ...] = SYMBOLS
    backtest_days: int = 30
    poll_interval: int = 5
    top_n: Optional[int] = 9999        # None = без ограничения
    force_recalc: bool = False
    full_recalc_mode: bool = False  # True = РУЧНОЙ полный пересчёт при запуске (в любой день); False = авторежим (будни лайт, выходные полный)
    auto_weekend_recalc: bool = True  # True = автоматический ПОЛНЫЙ пересчёт в выходные (Сб/Вс); False = только ручной запуск
    full_recalc_min_gap_days: int = 5  # мин. интервал (дней) между АВТО-ПОЛНЫМИ пересчётами: если полный был в последние N дней — повторно не запускаем
    night_backtest_hour: int = 3
    connection_timeout_sec: int = 300
    connection_warn_every_sec: int = 600
    journal_save_every_sec: int = 300
    magic_base: int = 770000


@dataclass(frozen=True)
class TrailParams:
    """Параметры трейлинг-стопа (ATR chandelier, модуль trail_manager.py).

    enabled=False — трейл выключен: SL остаётся как задан стратегией.
    Дистанция трейла = ATR(D1, atr_period) * atr_multiplier.
    """
    enabled: bool = True
    atr_period: int = 14
    atr_multiplier: float = 1.5
    check_interval_sec: int = 60
    min_move_points: int = 10  # не двигать SL, если выигрыш меньше (защита от спама)


@dataclass(frozen=True)
class SteeringParams:
    """Параметры «штурвала» — плавного перераспределения квот (wheel.py).

    Считается на основе РЕАЛЬНЫХ сделок из журнала (последние n_last_trades),
    вызывается в конце ночного пересчёта. Флаг enabled=False — квоты не трогаем.
    """
    enabled: bool = False
    alpha = 0.3
    min_q = 0.005       # снижаем пол
    max_q = 0.5         # поднимаем потолок
    score_mode = 'pnl'
    gamma = 1.5          # <-- НОВЫЙ ПАРАМЕТР: усиление лидеров
    n_last_trades = 10
    min_trades = 3      # <-- подними с 2 до 3 (для фильтра шума)
    max_dd: float = 0.15      # предел просадки (15%)
    score_mode: str = 'pnl'   # 'pnl' — вес по прибыли (как вкладка Strategies); 'sharpe' — pnl/vol
    quotas_file: str = 'steering_quotas.json'


# ═══════════════ ФАБРИКА ПО УМОЛЧАНИЮ ═══════════════
def build_default_strategy_params() -> StrategyParams:
    """Строит StrategyParams из RANGE-спек выше (то же, что делал main.py)."""
    return StrategyParams(
        # Stochastic
        k_periods=int_range(*K_PERIOD_RANGE),
        sl_points_list=int_range(*SL_POINTS_RANGE),
        tp_points_list=int_range(*TP_POINTS_RANGE),
        # Parabolic
        parabolic_steps=float_range(*PARABOLIC_STEP_RANGE),
        parabolic_maxs=float_range(*PARABOLIC_MAX_RANGE),
        # Moving Average
        ma_periods=int_range(*MA_PERIOD_RANGE),
        # Random Forest
        rf_lookbacks=int_range(*RF_LOOKBACK_RANGE),
        rf_nbars=int_range(*RF_NBARS_RANGE),
        rf_thresholds=float_range(*RF_THRESHOLD_RANGE),
        # Logistic Regression
        logreg_lookbacks=int_range(*LOGREG_LOOKBACK_RANGE),
        logreg_nbars=int_range(*LOGREG_NBARS_RANGE),
        logreg_thresholds=float_range(*LOGREG_THRESHOLD_RANGE),
        # MACD Cross
        macd_cross_fast_list=int_range(*MACD_CROSS_FAST_RANGE),
        macd_cross_slow_list=int_range(*MACD_CROSS_SLOW_RANGE),
        macd_cross_signal_list=int_range(*MACD_CROSS_SIGNAL_RANGE),
        # RSI Reversal
        rsi_rev_period_list=int_range(*RSI_REV_PERIOD_RANGE),
        rsi_rev_oversold_list=int_range(*RSI_REV_OVERSOLD_RANGE),
        rsi_rev_overbought_list=int_range(*RSI_REV_OVERBOUGHT_RANGE),
        # Bollinger
        bb_period_list=int_range(*BB_PERIOD_RANGE),
        bb_std_list=float_range(*BB_STD_RANGE),
        volume_period_list=int_range(*VOLUME_PERIOD_RANGE),
        # EMA Crossover
        ema_fast_list=int_range(*EMA_FAST_RANGE),
        ema_slow_list=int_range(*EMA_SLOW_RANGE),
        # RSI Divergence
        rsi_div_period_list=int_range(*RSI_DIV_PERIOD_RANGE),
        rsi_div_lookback_list=int_range(*RSI_DIV_LOOKBACK_RANGE),
        rsi_div_threshold_list=float_range(*RSI_DIV_THRESHOLD_RANGE),
        # Ichimoku
        tenkan_list=int_range(*TENKAN_RANGE),
        kijun_list=int_range(*KIJUN_RANGE),
        senkou_b_list=int_range(*SENKOU_B_RANGE),
        displacement_list=int_range(*DISPLACEMENT_RANGE),
        # Z-score
        zscore_sma_period_list=int_range(*ZSCORE_SMA_PERIOD_RANGE),
        zscore_threshold_list=float_range(*ZSCORE_THRESHOLD_RANGE),
        zscore_vol_period_list=int_range(*ZSCORE_VOL_PERIOD_RANGE),
        # Autocorrelation
        autocorr_lag_list=int_range(*AUTOCORR_LAG_RANGE),
        autocorr_threshold_list=float_range(*AUTOCORR_THRESHOLD_RANGE),
        autocorr_vol_period_list=int_range(*AUTOCORR_VOL_PERIOD_RANGE),
        # Hurst
        hurst_window_list=int_range(*HURST_WINDOW_RANGE),
        hurst_trend_threshold_list=float_range(*HURST_TREND_THRESHOLD_RANGE),
        hurst_vol_period_list=int_range(*HURST_VOL_PERIOD_RANGE),
        # Linear Regression Channel
        lrc_period_list=int_range(*LRC_PERIOD_RANGE),
        lrc_std_threshold_list=float_range(*LRC_STD_THRESHOLD_RANGE),
        lrc_vol_period_list=int_range(*LRC_VOL_PERIOD_RANGE),
        # Percentile
        pct_period_list=int_range(*PCT_PERIOD_RANGE),
        pct_low_list=int_range(*PCT_LOW_RANGE),
        pct_high_list=int_range(*PCT_HIGH_RANGE),
        pct_vol_period_list=int_range(*PCT_VOL_PERIOD_RANGE),
        # Runs Test
        runs_window_list=int_range(*RUNS_WINDOW_RANGE),
        runs_threshold_list=float_range(*RUNS_THRESHOLD_RANGE),
        runs_vol_period_list=int_range(*RUNS_VOL_PERIOD_RANGE),
        # Cointegration
        coint_window_list=int_range(*COINT_WINDOW_RANGE),
        coint_threshold_list=float_range(*COINT_THRESHOLD_RANGE),
        coint_beta_period_list=int_range(*COINT_BETA_PEROID_RANGE),
        # Rolling Sharpe
        sharpe_window_list=int_range(*SHARPE_WINDOW_RANGE),
        sharpe_threshold_list=float_range(*SHARPE_THRESHOLD_RANGE),
        sharpe_vol_period_list=int_range(*SHARPE_VOL_PERIOD_RANGE),
        # Skewness
        skew_window_list=int_range(*SKEW_WINDOW_RANGE),
        skew_threshold_list=float_range(*SKEW_THRESHOLD_RANGE),
        skew_vol_period_list=int_range(*SKEW_VOL_PERIOD_RANGE),
        # Bayesian
        bayes_window_list=int_range(*BAYES_WINDOW_RANGE),
        bayes_threshold_list=float_range(*BAYES_THRESHOLD_RANGE),
        bayes_prior_list=float_range(*BAYES_PRIOR_RANGE),
        # Kurtosis
        kurt_window_list=int_range(*KURT_WINDOW_RANGE),
        kurt_threshold_list=float_range(*KURT_THRESHOLD_RANGE),
        kurt_vol_period_list=int_range(*KURT_VOL_PERIOD_RANGE),
        # Chi-square
        chisq_window_list=int_range(*CHISQ_WINDOW_RANGE),
        chisq_entry_list=float_range(*CHISQ_ENTRY_RANGE),
        chisq_exit_list=float_range(*CHISQ_EXIT_RANGE),
        chisq_vol_period_list=int_range(*CHISQ_VOL_PERIOD_RANGE),
        # VWAP Reversion
        vwap_vol_period_list=int_range(*VWAP_VOL_PERIOD_RANGE),
        vwap_std_mult_list=float_range(*VWAP_STD_MULT_RANGE),
        # Momentum Breakout
        momentum_period_list=int_range(*MOMENTUM_PERIOD_RANGE),
        momentum_threshold_list=float_range(*MOMENTUM_THRESHOLD_RANGE),
        # Pin Bar Reversal
        pin_bar_body_ratio_list=float_range(*PIN_BAR_BODY_RATIO_RANGE),
        # Prev Daily Candle Direction
        prev_daily_hold_bars_list=int_range(*PREV_DAILY_HOLD_BARS_RANGE),
        # Rolling Correlation Momentum
        corr_window_list=int_range(*CORR_WINDOW_RANGE),
        corr_threshold_list=float_range(*CORR_THRESHOLD_RANGE),
    )


def build_default_configs() -> "AppContext":
    """Собирает полный контекст приложения с настройками по умолчанию."""
    return AppContext(
        symbols=list(SYMBOLS),
        strategy_params=build_default_strategy_params(),
        risk_params=RiskParams(),
        backtest_config=BacktestConfig(),
        trail_params=TrailParams(),
        steering_params=SteeringParams(),
    )


@dataclass(frozen=True)
class AppContext:
    """Полный контекст приложения."""
    symbols: List[str]
    strategy_params: StrategyParams
    risk_params: RiskParams
    backtest_config: BacktestConfig
    trail_params: TrailParams
    steering_params: SteeringParams