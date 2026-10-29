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
           "USDCADrfd", "AUDUSDrfd", "NZDUSDrfd",
           "XAUUSDrfd", "XAGUSDrfd")   # 29.10.2026: металлы (сетка SL/TP ниже)

K_PERIOD_RANGE = (7, 28, 7)
SL_POINTS_RANGE = (300, 1200, 450)   # -> [300, 750, 1200] (ровный шаг, без дублей хвоста)
TP_POINTS_RANGE = (300, 1200, 450)   # -> [300, 750, 1200]

# ── SL/TP сетка: пер-символьная (полоса в % цены, а не одни пункты на всех) ──
# Было: одна сетка в ПУНКТАХ на все пары. Пункт у пар разный (0.00001 у 5-значных,
# 0.001 у JPY), поэтому одна и та же цифра означала разный риск: 1200 пунктов =
# 0.77% по USDJPY, 1.07% по EURUSD и 2.11% по NZDUSD.
# Стало: общая полоса 0.30 / 0.60 / 0.90% от цены (≈0.5/1.0/1.5 дневного ATR),
# а пункты посчитаны по ЯКОРНОЙ цене символа (указана в комментарии к строке).
# ЯКОРЬ: цена на 25.10.2026. При уходе цены на ±10% полоса в % сместится на ±10%.
SLTP_PCT_GRID = (0.0030, 0.0090, 0.0030)   # целевая полоса: 0.3 / 0.6 / 0.9 % от цены

SL_POINTS_GRID = {
    'EURUSDrfd': (350, 1000,  325),   # [350,  675, 1000]  -> 0.31 / 0.60 / 0.89% @1.1200
    'GBPUSDrfd': (400, 1200,  400),   # [400,  800, 1200]  -> 0.30 / 0.60 / 0.90% @1.3370
    'USDJPYrfd': (450, 1350,  450),   # [450,  900, 1350]  -> 0.29 / 0.57 / 0.86% @156.8
    'USDCHFrfd': (250,  750,  250),   # [250,  500,  750]  -> 0.30 / 0.61 / 0.91% @0.8250
    'USDCADrfd': (400, 1200,  400),   # [400,  800, 1200]  -> 0.29 / 0.57 / 0.86% @1.4012
    'AUDUSDrfd': (200,  650,  225),   # [200,  425,  650]  -> 0.28 / 0.60 / 0.92% @0.7039
    'NZDUSDrfd': (175,  525,  175),   # [175,  350,  525]  -> 0.31 / 0.61 / 0.92% @0.5699
    # ── Металлы (29.10.2026): та же полоса 0.3/0.6/0.9% от цены, пункты по якорю.
    #    Спред в % цены: XAU 0.011% (дешевле EURUSD 0.0125%), XAG 0.036% (~3x дороже),
    #    поэтому у серебра полоса сдвинута вверх: самый узкий SL остаётся >=10 спредов.
    'XAUUSDrfd': (1200, 3600, 1200),  # [1200, 2400, 3600] -> 0.30 / 0.60 / 0.90% @4016.85; 27/53/80 спредов
    'XAGUSDrfd': (2000, 5000, 1500),  # [2000, 3500, 5000] -> 0.38 / 0.67 / 0.96% @52.20;   10/18/26 спредов
}
TP_POINTS_GRID = SL_POINTS_GRID          # TP из той же сетки (как и раньше: 9 пар SL×TP)


def sl_tp_points_for(symbol):
    """(SL, TP) в пунктах для символа. Фолбэк — SL_POINTS_RANGE (символ вне словаря).

    У всех пар гарантированно ОДИНАКОВОЕ число шагов (3: два промежуточных + граница) —
    на этом держатся счётчики комбинаций вида len(SL_POINTS_LIST) * len(TP_POINTS_LIST).
    """
    sl_rng = SL_POINTS_GRID.get(symbol, SL_POINTS_RANGE)
    tp_rng = TP_POINTS_GRID.get(symbol, TP_POINTS_RANGE)
    return int_range(*sl_rng), int_range(*tp_rng)

# ── Фонд: метрики жизненного цикла (для дэшборда) ──
# FUND_START_DATE: первый день НЕПРЕРЫВНОЙ активной торговли текущего фонда.
# 29.09.2026 — из истории MT5: с этого дня поток сделок идёт всем набором стратегий
# (ранние разовые заходы не считаем: 18.09.2026 — создание demo-счёта, 3 сделки по 0.1;
# 03–09.09 — чужой EA, magic 29082026/20240907; 10–15.09 — ручные пробы).
# Поэтому якорь — константа, а не MIN(time) из deals: тот «омолодится» старыми сделками.
FUND_START_DATE = '2026-09-29'

# ── Фильтр «плата за риск» (отсев комбинаций SL/TP на входе) ──
# MIN_TP_SL_RATIO: минимальное номинальное TP/SL. 0.5 = не берём комбинации,
#   где цель меньше половины риска (SL=1200 / TP=300 → 0.25 → отсев).
# MIN_PAYOFF: минимальная ФАКТИЧЕСКАЯ плата по бэктесту — средний выигрыш /
#   средний проигрыш = PF·(1−WR)/WR. 0.6 = не больше 1.67 проигрыша на выигрыш.
MIN_TP_SL_RATIO = 0.5
MIN_PAYOFF = 0.6
PARABOLIC_STEP_RANGE = (0.02, 0.2, 0.02)
PARABOLIC_MAX_RANGE = (0.2, 0.4, 0.05)
MA_PERIOD_RANGE = (10, 200, 25)

RF_LOOKBACK_RANGE = (200, 400, 100)
RF_NBARS_RANGE = (5, 10, 5)
RF_THRESHOLD_RANGE = (0.55, 0.65, 0.10)
RF_RETRAIN_EVERY = 100   # walk-forward: переобучение модели каждые N баров

LOGREG_LOOKBACK_RANGE = (200, 400, 100)
LOGREG_NBARS_RANGE = (6, 12, 6)
LOGREG_THRESHOLD_RANGE = (0.55, 0.65, 0.10)
LOGREG_RETRAIN_EVERY = 100   # walk-forward: переобучение модели каждые N баров

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
EMA_FAST_RANGE = (8, 12, 2)          # -> [8, 10, 12] (шаг 1 давал почти дубли)
EMA_SLOW_RANGE = (18, 24, 3)

# RSI Divergence
RSI_DIV_PERIOD_RANGE = (12, 16, 2)
RSI_DIV_LOOKBACK_RANGE = (4, 7, 1)
RSI_DIV_THRESHOLD_RANGE = (0.4, 0.6, 0.1)

# Ichimoku
TENKAN_RANGE = (8, 12, 4)            # -> [8, 12] (было [7,11,12] — хвост шага 1)
KIJUN_RANGE = (22, 30, 4)
SENKOU_B_RANGE = (45, 55, 5)
DISPLACEMENT_RANGE = (22, 30, 4)

# Z-score reversion
ZSCORE_SMA_PERIOD_RANGE = (20, 50, 10)
ZSCORE_THRESHOLD_RANGE = (1.5, 2.5, 0.5)
ZSCORE_VOL_PERIOD_RANGE = (15, 15, 5)    # схлопнуто: calc_zscore считает vol_ma, но вход/выход его не читают

# Autocorrelation momentum
AUTOCORR_LAG_RANGE = (1, 5, 2)
AUTOCORR_THRESHOLD_RANGE = (0.2, 0.4, 0.1)
AUTOCORR_VOL_PERIOD_RANGE = (15, 15, 5)  # схлопнуто: vol_period в calc_autocorrelation не используется

# Hurst regime filter
HURST_WINDOW_RANGE = (20, 60, 10)
HURST_TREND_THRESHOLD_RANGE = (0.5, 0.7, 0.1)
HURST_VOL_PERIOD_RANGE = (20, 20, 10)    # схлопнуто: calc_hurst не принимает vol_period

# Linear Regression Channel
LRC_PERIOD_RANGE = (20, 50, 10)
LRC_STD_THRESHOLD_RANGE = (1.5, 2.5, 0.5)
LRC_VOL_PERIOD_RANGE = (15, 15, 5)       # схлопнуто: модуль LRC vol_period не принимает

# Percentile reversion
PCT_PERIOD_RANGE = (20, 50, 10)
PCT_LOW_RANGE = (3, 7, 2)            # -> [3, 5, 7] (было [3,5,7,8] — хвост шага 1)
PCT_HIGH_RANGE = (93, 97, 2)         # -> [93, 95, 97] (было [92,94,96,97] — хвост шага 1)
PCT_VOL_PERIOD_RANGE = (15, 15, 5)       # схлопнуто: модуль percentile vol_period не принимает

# Runs Test trend
RUNS_WINDOW_RANGE = (20, 50, 10)
RUNS_THRESHOLD_RANGE = (1.5, 2.0, 0.2)
RUNS_VOL_PERIOD_RANGE = (15, 15, 5)      # схлопнуто: модуль runs vol_period не принимает

# Cointegration pairs
COINT_WINDOW_RANGE = (20, 60, 10)
COINT_THRESHOLD_RANGE = (1.5, 2.5, 0.5)
COINT_BETA_PEROID_RANGE = (20, 20, 10)   # схлопнуто: beta_period в _backtest_coint захардкожен (0.0)

# Rolling Sharpe filter
SHARPE_WINDOW_RANGE = (20, 60, 10)
SHARPE_THRESHOLD_RANGE = (0.3, 0.7, 0.1)
SHARPE_VOL_PERIOD_RANGE = (15, 15, 5)    # схлопнуто: _backtest_sharpe передаёт 0.0 вместо vol_period

# Skewness extreme
SKEW_WINDOW_RANGE = (20, 50, 10)
SKEW_THRESHOLD_RANGE = (0.8, 1.2, 0.2)
SKEW_VOL_PERIOD_RANGE = (15, 15, 5)      # схлопнуто: _backtest_skewness передаёт 0.3 вместо vol_period

# Bayesian trend update
BAYES_WINDOW_RANGE = (20, 50, 10)
BAYES_THRESHOLD_RANGE = (0.6, 0.7, 0.05)
BAYES_PRIOR_RANGE = (0.4, 0.6, 0.1)

# Kurtosis spike
KURT_WINDOW_RANGE = (20, 60, 10)
KURT_THRESHOLD_RANGE = (3.0, 6.0, 1.0)
KURT_VOL_PERIOD_RANGE = (15, 15, 5)      # схлопнуто: _backtest_kurtosis передаёт 3.0/1.0 вместо vol_period

# Chi-square distribution
CHISQ_WINDOW_RANGE = (20, 50, 10)
CHISQ_ENTRY_RANGE = (0.03, 0.07, 0.02)
CHISQ_EXIT_RANGE = (0.15, 0.25, 0.05)
CHISQ_VOL_PERIOD_RANGE = (15, 15, 5)     # схлопнуто: модуль chi_square vol_period не принимает

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

# Williams %R Extreme
WILLIAMS_R_PERIOD_RANGE = (10, 20, 5)

# MACD Histogram Reversal
MACD_HISTOGRAM_FAST_RANGE = (8, 12, 2)
MACD_HISTOGRAM_SLOW_RANGE = (20, 26, 3)
MACD_HISTOGRAM_SIGNAL_RANGE = (3, 6, 1)

# BB Squeeze Breakout
BB_SQUEEZE_PERIOD_RANGE = (15, 25, 5)
BB_SQUEEZE_STD_RANGE = (1.5, 2.5, 0.5)
BB_SQUEEZE_PCT_RANGE = (0.3, 0.7, 0.1)

# Donchian Breakout
DONCHIAN_PERIOD_RANGE = (15, 25, 5)

# Engulfing Pattern
ENGULFING_PERIOD_RANGE = (1, 1)  # no params, single value

# CCI Reversion
CCI_PERIOD_RANGE = (10, 20, 5)
CCI_THRESHOLD_RANGE = (80, 120, 20)

# SuperTrend
SUPERTREND_PERIOD_RANGE = (7, 14, 3)
SUPERTREND_MULTIPLIER_RANGE = (2.0, 4.0, 0.5)

# ADX Trend
ADX_PERIOD_RANGE = (10, 20, 3)
ADX_THRESHOLD_RANGE = (20, 30, 3)

# OBV Flow
OBV_PERIOD_RANGE = (15, 30, 5)
OBV_THRESHOLD_RANGE = (0.3, 0.7, 0.1)

# Morning/Evening Star
MORNING_STAR_BODY_RATIO_RANGE = (0.2, 0.4, 0.1)


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
    # Williams %R Extreme
    williams_r_period_list: Tuple[int, ...]
    # MACD Histogram Reversal
    macd_histogram_fast_list: Tuple[int, ...]
    macd_histogram_slow_list: Tuple[int, ...]
    macd_histogram_signal_list: Tuple[int, ...]
    # BB Squeeze Breakout
    bb_squeeze_period_list: Tuple[int, ...]
    bb_squeeze_std_list: Tuple[float, ...]
    bb_squeeze_pct_list: Tuple[float, ...]
    # Donchian Breakout
    donchian_period_list: Tuple[int, ...]
    # Engulfing Pattern
    engulfing_dummy: Tuple[int, ...]  # placeholder — no params
    # CCI Reversion
    cci_period_list: Tuple[int, ...]
    cci_threshold_list: Tuple[int, ...]
    # SuperTrend
    supertrend_period_list: Tuple[int, ...]
    supertrend_multiplier_list: Tuple[float, ...]
    # ADX Trend
    adx_period_list: Tuple[int, ...]
    adx_threshold_list: Tuple[int, ...]
    # OBV Flow
    obv_period_list: Tuple[int, ...]
    obv_threshold_list: Tuple[float, ...]
    # Morning/Evening Star
    morning_star_body_ratio_list: Tuple[float, ...]


@dataclass(frozen=True)
class RiskParams:
    """Параметры риск-менеджмента."""
    max_total_positions: int = 999999   # общий лимит отменён
    max_per_side: int = 99999               # лимит на сторону расширен (наблюдение за всеми стратегиями)
    max_per_type: int = 8               # макс. стратегий ОДНОГО типа (rf, logreg, ...) в активном топе — диверсификация (5 → 8, 28.10: шире состав)
    max_per_symbol: int = 99999             # лимит на символ расширен (наблюдение за всеми стратегиями)
    daily_loss_limit_pct: float = 3.0
    equity_stop_pct: float = 10.0
    # ── Маржа (margin level) — защита от margin call ──
    # min_margin_level_pct: перед открытием прогнозируем уровень маржи ПОСЛЕ сделки;
    #   если он упадёт ниже — ордер не отправляем (плюс runtime-предупреждение).
    # margin_level_stop_pct: аварийное сокращение позиций при падении уровня ниже.
    min_margin_level_pct: float = 150.0
    margin_level_stop_pct: float = 100.0
    realtime_quota_recalc: bool = True
    quota_recalc_interval_sec: int = 300
    min_sl_distance_points: int = 10
    max_sl_distance_points: int = 6000   # 5000 -> 6000: верхняя точка сетки XAGUSDrfd = 5000 pt

    max_risk_pct: float = 0.3
    # Кап риска на ОДНУ сделку (доля баланса). Широкий SL + большая квота больше
    # не дают «-20k одной сделкой»: лот режется до balance*pct / sl_money.
    per_trade_risk_pct: float = 0.005
    min_lot: float = 0.01
    # Hard cap for the live plan size (number of strategy slots). Breadth is
    # limited by the quota / min_lot budget: 40 slots is wider than the old 20-23.
    plan_max_strategies: int = 40
    # Ceiling for ONE strategy is a MONEY rule, not a lot constant
    # (see risk_manager.lot_ceiling_money):
    #   cap = min(balance*per_trade_risk_pct / sl_money_per_lot,
    #             balance*risk_1000_points_pct / money_per_1000_points)
    # Calibration behind risk_1000_points_pct: 0.5 lot of USDJPY on a 1000-point
    # move costs 0.5 * 1000 * 0.001 * 100 000 = 50 000 JPY = ~25 300 RUB, i.e.
    # 2.53% of a 1 000 000 RUB deposit. 2.5% keeps the plan leader at ~0.5 lot at
    # today's balance and scales automatically with the balance.
    risk_1000_points_pct: float = 0.025






    min_score: float = 1.0
    # Значимость вместо жёсткого порога «10 сделок»: t-статистика ожидания
    # на сделку. 2.5 ≈ 98.8% на ОДНУ гипотезу; по 6265 уникальным комбинациям
    # ожидаемо ~39 «шумовых» проходов (было ~8 при 3.0) — добивает score + max_per_type.
    min_tstat: float = 2.5
    # ── Гейт квоты категории на вход (strategy_engine.quota_gate_check) ──
    # План (distribute_lots) строится по бэктесту и открытые сделки не видит.
    # True: новый вход разрешён только если риск, УЖЕ занятый категорией
    # «символ + семейство» (лот × деньги риска по SL открытых позиций),
    # меньше её доли риск-квоты из journals/steering_quotas.json.
    # Первая позиция категории открывается всегда: min_lot не дробится,
    # иначе категория с крошечной квотой не смогла бы торговать вовсе.
    quota_gate_enabled: bool = True


@dataclass(frozen=True)
class PeakTrimParams:
    """Параметры «пик-трима» — частичной фиксации по ИСТОРИЧЕСКОМУ пику.

    Замысел: сэмплер trades_db пишет в position_peak пик нереализованной прибыли
    каждой сделки (в ₽ и в ₽/лот). По истории (lookback_days, без сегодняшнего
    дня) считаем эталон — p90 засечённых peak_per_lot по ВСЕМУ пулу сделок
    (без разреза по категориям/стратегиям — сравниваем со всей книгой). Если
    текущая сделка в моменте даёт >= pct от эталона — фиксируем почти всё,
    оставляя keep_volume (0.01), чтобы остаток продолжал обновлять пики.

    enabled=False по умолчанию: модуль только ЛОГИРУЕТ решения ([TRIM] would …),
    реальные закрытия включаются флагом и требуют проверки на истории.
    """
    enabled: bool = False          # True = РЕАЛЬНО закрывать; False = только лог
    shadow: bool = True            # логировать решения даже при enabled=False
    pct: float = 0.75              # порог от исторического эталона (0.80 / 0.85 — обсуждается)
    keep_volume: float = 0.01      # что оставляем от позиции (для сбора статистики)
    lookback_days: int = 30        # окно истории эталона, ДНИ ДО сегодняшнего
    lookback_days: int = 30        # окно истории эталона, ДНИ ДО сегодняшнего
    ref_quantile: float = 0.90     # агрегат эталона: p90 по ВСЕМ сделкам пула
    min_ref_per_lot: float = 500.0  # эталон меньше (₽/лот) — шум, не триггеримся
    min_money: float = 100.0       # текущая прибыль позиции меньше (₽) — не трогаем
    log_from_pct: float = 0.5      # логировать «почти дотянул» начиная с 50% эталона
    single_shot: bool = True       # 1 трим на позицию в день


@dataclass(frozen=True)
class BacktestConfig:
    """Конфигурация бэктеста и демона."""
    symbols: Tuple[str, ...] = SYMBOLS
    backtest_days: int = 90   # окно 30 → 90 (28.10): t-стат растёт как √n, при n×3
                              # порог 2.5 пробивает заметно больше семейств.
                              # Факт: полный проход на 30 дн. = 12 мин (3 процесса,
                              # 28.10 03:00→03:12), значит 90 дн. ≈ 35–40 мин.
                              # На время прогона торговля не стоит: план прежний.
    poll_interval: int = 5
    # Breadth of the ranking: the best combo of EVERY family (symbol + type) gets
    # a row even if it cannot pass the t-stat test. Quality gates stay in
    # strategy_engine.deduplicate_results: n_trades >= min_trades_rank, profit > 0,
    # score >= min_score and the TP/SL payoff filter.
    rank_all_families: bool = True
    min_trades_rank: int = 10
    max_per_symbol_pct: float = 0.30
    top_n: Optional[int] = 9999        # None = без ограничения
    force_recalc: bool = False
    full_recalc_mode: bool = True  # True = РУЧНОЙ полный пересчёт при запуске (в любой день); False = авторежим (будни реранк по чекпойнтам, выходные полный)
    auto_weekend_recalc: bool = True  # True = автоматический ПОЛНЫЙ пересчёт в выходные (Сб/Вс); False = только ручной запуск
    full_recalc_daily: bool = True  # True = обновлять ВСЮ корзину каждую ночь (окно выходных не учитывается).
    # 27.10: включено решением от 27.10 — полный проход ставится
    # фоновым job (async_backtest), цикл не блокируется, маркер пишется по завершении.
    # ВРЕМЕННО False (22.10): полный пересчёт — синхронный вызов в боевом цикле и держит его
    # закрытым 150–230 мин. Включаем обратно, когда пересчёт будет вынесен в фоновый job
    # (backtest_job.BacktestJob + приём результата в цикле), то есть когда блокировки не будет.
    async_backtest: bool = True   # True = ПОЛНЫЙ пересчёт считается в фоновом потоке: боевой
                                  # цикл продолжает жить (бары, сигналы, трейлинг, аварийные
                                  # защиты), результат применяется по завершении job.
                                  # False = старое поведение (синхронный проход внутри цикла).
    full_recalc_only_flat: bool = False  # True = откладывать ПОЛНЫЙ пересчёт, пока есть открытые позиции
    full_recalc_min_gap_days: int = 1  # мин. интервал (дней) между АВТО-ПОЛНЫМИ пересчётами: если полный был в последние N дней — повторно не запускаем
    night_backtest_hour: int = 3
    # incremental_bars УДАЛЕНО: в проекте только ПОЛНЫЕ пересчёты, инкремента нет.
                                    # семейства exact/exp — по срезу с warm-up, cum/model —
                                    # полным окном. Включать только после parity (strategies/_warmup.py).
    # incremental_warmup_bars УДАЛЕНО вместе с инкрементом.
    calc_cache: bool = True  # True = свёртка SL/TP: подготовка (calc_*) считается 1 раз на комбинацию
                             # параметров, а не на каждую из 9 пар SL/TP (см. strategies/_calc_cache.py).
                             # False = откат к прежнему поведению (расчёт на каждую пару).
    numpy_loop: bool = True  # True = быстрая петля бэктеста на numpy-массивах вместо df['col'].iloc[i]
                             # (strategies/_bt_core.py). False = прежний iloc-цикл (эталон паритета,
                             # откат одной строкой). Гейт: python tools/loop_parity.py
    full_refresh_window_end_hour: int = 10  # Конец "окна выходных" (полный проход в будни ставится с 03:00 до этого часа). 27.10: возвращено 10.
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
    enabled: bool = False
    atr_period: int = 14
    atr_multiplier: float = 2.3
    check_interval_sec: int = 60
    min_move_points: int = 10  # не двигать SL, если выигрыш меньше (защита от спама)


@dataclass(frozen=True)
class SteeringParams:
    """Параметры «штурвала» — плавного перераспределения квот (wheel.py).

    Считается на основе РЕАЛЬНЫХ сделок из журнала (последние n_last_trades),
    вызывается в конце ночного пересчёта. Флаг enabled=False — квоты не трогаем.
    """
    enabled: bool = True
    alpha = 1.0          # 1.0 = полная перекладка к цели (tree=wheel, зелёное получает объём сразу); <1.0 — EMA-сглаживание
    min_q = 0.0035      # пол квоты: 0.005 → 0.0035 (мягко). При 84 категориях пол
                        # съедал ~80% бюджета; 0.0035 отдаёт зелёным ~+4 п.п.
    max_q = 0.065       # потолок штурвала: 0.05 → 0.065 (мягко). Лидер может взять
                        # 6.5% доли вместо 5%, но не больше
                        # (было 0.10 — одна категория могла взять десятую часть риск-бюджета)
    score_mode = 'pnl_per_lot'   # штурвал: 'pnl' — абсолютный PnL; 'pnl_per_lot' — удельный (₽ за лот); 'sharpe' — pnl/vol
    gamma = 1.5          # усиление лидеров; для 'pnl_per_lot' баллы в узком диапазоне — подбирать 2.0–3.0
    n_last_trades = 10
    score_volume_prior: float = 0.0   # shrinkage ₽/лот: score = PnL / (volume + V₀); 0.0 → авто-медиана объёма по оцениваемым категориям
    min_trades = 10      # фильтр шума: категория с <10 сделками за окно не скорится → min_q
    max_dd: float = 0.15      # предел просадки (15%)
    score_mode: str = 'pnl_per_lot'   # 'pnl' — абсолютный PnL (как Strategy Tree); 'pnl_per_lot' — удельный ₽/лот; 'sharpe' — pnl/vol
    quotas_file: str = 'steering_quotas.json'
    tree_weighting: bool = True   # True: объём активации считается от реальных сделок (бэктест выбирает, Tree задаёт объём). ВКЛ.
    # ЖЁСТКИЙ период аллокации (дни). Единый источник и для Strategy Tree,
    # и для Wheel, и для ночной перекладки объёма в main.py. Слайдер дэшборда
    # его НЕ меняет — это только визуальный просмотр. Стратегии деградируют,
    # поэтому считаем прибыль за свежее окно, а не за всю историю.
    lookback_days: int = 30   # 14 → 30: за 14 дней половина категорий не набирала
                              # min_trades=10 и садилась на «пол» min_q. Дэшборд
                              # берёт это же значение (dashboard.ALLOC_DAYS).
    # ── Политика потерь (kill switch по реальным сделкам) ──
    # Убыточная категория НЕ получает пол min_q: сначала карантин (квота ×
    # loss_decay), при убытке больше порога — квота 0 и торговля по категории
    # останавливается. Порог: доля риск-квоты счёта (2%) ИЛИ абсолютный рубль.
    loss_decay: float = 0.20      # карантин: 0.25 → 0.20 — убыточная получает меньше (мягкий шаг)
    kill_pnl_pct: float = 0.02    # убыток > 2% риск-квоты → q=0 (полная остановка категории)
    kill_pnl_rub: float = 0.0     # абсолютный порог ₽ (0 = выключен, работает только %) 
    kill_min_trades: int = 3      # сделок в окне, чтобы карать (ниже min_trades: скорить нельзя, карать можно)
    # Периодичность ОБЯЗАТЕЛЬНОГО пересчёта штурвала в рабочем цикле (сек).
    # Штурвал больше не привязан к ночному бэктесту: он отрабатывает при старте,
    # сразу после ночного пересчёта и далее каждые interval_sec.
    interval_sec: int = 3600
    # ── Премия/дисконт к объёму по лучшей/худшей тактике входа (tactic_tilt.py) ──
    # Лучшая связка «пара + день выхода» получает +tactic_tilt_pct к объёму,
    # худшая — столько же в минус. Применяется В САМОМ КОНЦЕ реранка (после
    # штурвала), поэтому Daily Plan показывает уже объём С надбавкой.
    tactic_tilt_enabled: bool = True
    tactic_tilt_pct: float = 0.20            # ±20% к объёму
    tactic_tilt_window_days: int = 90        # вся история, но не больше 90 дней
    tactic_tilt_min_trades: int = 2          # связка с 1 сделкой — шум
    tactic_tilt_weekday_only: bool = False   # True: только в день входа тактики


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
        # Williams %R Extreme
        williams_r_period_list=int_range(*WILLIAMS_R_PERIOD_RANGE),
        # MACD Histogram Reversal
        macd_histogram_fast_list=int_range(*MACD_HISTOGRAM_FAST_RANGE),
        macd_histogram_slow_list=int_range(*MACD_HISTOGRAM_SLOW_RANGE),
        macd_histogram_signal_list=int_range(*MACD_HISTOGRAM_SIGNAL_RANGE),
        # BB Squeeze Breakout
        bb_squeeze_period_list=int_range(*BB_SQUEEZE_PERIOD_RANGE),
        bb_squeeze_std_list=float_range(*BB_SQUEEZE_STD_RANGE),
        bb_squeeze_pct_list=float_range(*BB_SQUEEZE_PCT_RANGE),
        # Donchian Breakout
        donchian_period_list=int_range(*DONCHIAN_PERIOD_RANGE),
        # Engulfing Pattern
        engulfing_dummy=(1,),
        # CCI Reversion
        cci_period_list=int_range(*CCI_PERIOD_RANGE),
        cci_threshold_list=int_range(*CCI_THRESHOLD_RANGE),
        # SuperTrend
        supertrend_period_list=int_range(*SUPERTREND_PERIOD_RANGE),
        supertrend_multiplier_list=float_range(*SUPERTREND_MULTIPLIER_RANGE),
        # ADX Trend
        adx_period_list=int_range(*ADX_PERIOD_RANGE),
        adx_threshold_list=int_range(*ADX_THRESHOLD_RANGE),
        # OBV Flow
        obv_period_list=int_range(*OBV_PERIOD_RANGE),
        obv_threshold_list=float_range(*OBV_THRESHOLD_RANGE),
        # Morning/Evening Star
        morning_star_body_ratio_list=float_range(*MORNING_STAR_BODY_RATIO_RANGE),
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