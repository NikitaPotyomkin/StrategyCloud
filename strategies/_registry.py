"""Реестр standalone-стратегий (Task B: интеграция в LIVE).

Одна декларативная таблица вместо ручного дублирования по 5-6 точкам
(main.py / functions.py / strategy_engine.py). Функции-обёртки ниже делают всю
интеграцию generic-циклами, поэтому добавление новой стратегии = 1 запись в REGISTRY.

ВАЖНО: этот модуль НЕ путать с strategies/_bt_core.py (там движок бэктеста)
и с корневым strategy_engine.py (там live-исполнение).

Поля записи:
    module  — имя модуля в strategies/ (без .py)
    calc    — имя функции расчёта сигнала (пишет колонку 'k')
    entry   — имя check_entry(prev, curr) / check_entry(prev_k, curr_k)
    exit    — имя check_exit(prev, curr, direction)
    label   — короткий ярлык семейства (для отчётов/логов, уникален)
    grid    — список значений param_key (обычно период окна)
    min_len — минимальная длина df для live-расчёта (прогрев индикатора), default 2

Контракт standalone-модуля (единый для всех 81):
    calc_<name>(df, period) -> df с колонкой 'k'
    check_entry(prev, curr) -> bool
    check_exit(prev, curr, direction) -> bool
    backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0) -> (profit, n_trades, trade_profits)
"""
import importlib

REGISTRY = {
    # ── Пилотная группа (пункт 1): 5 простых однопараметрических стратегий ──
    'triple_ema': dict(
        module='triple_ema', calc='calc_triple_ema',
        entry='check_entry', exit='check_exit',
        label='TripleEMA', grid=[8, 10, 14, 20], min_len=120,
    ),
    'adx_di': dict(
        module='adx_di_crossover', calc='calc_adx_di',
        entry='check_entry', exit='check_exit',
        label='ADX-DI', grid=[7, 14, 21], min_len=120,
    ),
    'ultimate': dict(
        module='ultimate_oscillator', calc='calc_ultimate',
        entry='check_entry', exit='check_exit',
        label='UO', grid=[7, 14, 21], min_len=120,
    ),
    'cmo': dict(
        module='cmo_extreme', calc='calc_cmo',
        entry='check_entry', exit='check_exit',
        label='CMO', grid=[14, 20], min_len=60,
    ),
    'donchian_vol': dict(
        module='donchian_volume_filter', calc='calc_donchian_volume',
        entry='check_entry', exit='check_exit',
        label='DonchVol', grid=[10, 20, 55], min_len=60,
    ),

    # ── MA / тренд (батч 2) ──
    'ema2050': dict(
        module='ema_crossover_20_50', calc='calc_ema_cross',
        entry='check_entry', exit='check_exit',
        label='EMA2050', grid=[10, 20, 30, 50], min_len=200,
    ),
    'hull': dict(
        module='hull_ma_crossover', calc='calc_hull',
        entry='check_entry', exit='check_exit',
        label='Hull', grid=[10, 16, 27, 40], min_len=200,
    ),
    'ribbon': dict(
        module='ma_ribbon_expansion', calc='calc_ma_ribbon',
        entry='check_entry', exit='check_exit',
        label='Ribbon', grid=[10, 20], min_len=200,
    ),
    'dualema': dict(
        module='dual_ema_slope', calc='calc_dual_ema_slope',
        entry='check_entry', exit='check_exit',
        label='DualEMA', grid=[10, 20, 30], min_len=200,
    ),
    'macdline': dict(
        module='macd_line_crossover', calc='calc_macd_line',
        entry='check_entry', exit='check_exit',
        label='MACDLine', grid=[8, 12, 16], min_len=200,
    ),
    'macdema': dict(
        module='macd_ema_filter', calc='calc_macd_ema',
        entry='check_entry', exit='check_exit',
        label='MACDEMA', grid=[8, 12, 16], min_len=200,
    ),
    'vwmacd': dict(
        module='vw_macd', calc='calc_vw_macd',
        entry='check_entry', exit='check_exit',
        label='VWMACD', grid=[8, 12, 16], min_len=200,
    ),
    'wmaema': dict(
        module='wma_ema_filter', calc='calc_wma_ema',
        entry='check_entry', exit='check_exit',
        label='WMAEMA', grid=[10, 20, 30], min_len=200,
    ),
    'adxbreak': dict(
        module='adx_breakout_ema', calc='calc_adx_breakout_ema',
        entry='check_entry', exit='check_exit',
        label='ADXBreak', grid=[7, 14, 21], min_len=200,
    ),
    'momthr': dict(
        module='momentum_threshold', calc='calc_momentum_threshold',
        entry='check_entry', exit='check_exit',
        label='MomThr', grid=[5, 10, 20], min_len=200,
    ),
    'hhll': dict(
        module='hh_ll_sequence', calc='calc_hh_ll',
        entry='check_entry', exit='check_exit',
        label='HHLL', grid=[5, 10, 20], min_len=120,
    ),

    # ── Bollinger / сжатие (батч 3) ──
    'bbwalk': dict(
        module='bb_walk', calc='calc_bb_walk',
        entry='check_entry', exit='check_exit',
        label='BBWalk', grid=[10, 20, 30], min_len=120,
    ),
    'bbrsi': dict(
        module='bb_rsi_filter', calc='calc_bb_rsi',
        entry='check_entry', exit='check_exit',
        label='BBRsi', grid=[10, 20, 30], min_len=120,
    ),
    'bbmacd': dict(
        module='bb_macd', calc='calc_bb_macd',
        entry='check_entry', exit='check_exit',
        label='BBMacd', grid=[10, 20, 30], min_len=120,
    ),
    'adxbb': dict(
        module='adx_bb_squeeze', calc='calc_adx_bb_squeeze',
        entry='check_entry', exit='check_exit',
        label='ADXBB', grid=[7, 14, 21], min_len=120,
    ),

    # ── Каналы / осцилляторы (батч 3) ──
    'dpo': dict(
        module='dpo', calc='calc_dpo',
        entry='check_entry', exit='check_exit',
        label='DPO', grid=[10, 20, 30], min_len=120,
    ),
    'ppo': dict(
        module='ppo', calc='calc_ppo',
        entry='check_entry', exit='check_exit',
        label='PPO', grid=[10, 20, 30], min_len=120,
    ),
    'vortex': dict(
        module='vortex_crossover', calc='calc_vortex',
        entry='check_entry', exit='check_exit',
        label='Vortex', grid=[10, 14, 20], min_len=120,
    ),
    'roc': dict(
        module='roc_extreme', calc='calc_roc_extreme',
        entry='check_entry', exit='check_exit',
        label='ROC', grid=[10, 14, 20], min_len=120,
    ),
    'elder': dict(
        module='elder_impulse', calc='calc_elder_impulse',
        entry='check_entry', exit='check_exit',
        label='Elder', grid=[10, 14, 20], min_len=120,
    ),
    'forceidx': dict(
        module='force_index_trend', calc='calc_force_index',
        entry='check_entry', exit='check_exit',
        label='ForceIdx', grid=[10, 13, 20], min_len=120,
    ),
    'stochma': dict(
        module='stoch_ma_filter', calc='calc_stoch_ma',
        entry='check_entry', exit='check_exit',
        label='StochMA', grid=[10, 14, 20], min_len=120,
    ),
    'stochrsiema': dict(
        module='stoch_rsi_ema', calc='calc_stoch_rsi_ema',
        entry='check_entry', exit='check_exit',
        label='StochRSIEMA', grid=[10, 14, 20], min_len=160,
    ),
    'cciext': dict(
        module='cci_extreme_trend', calc='calc_cci_extreme_trend',
        entry='check_entry', exit='check_exit',
        label='CCIExt', grid=[14, 20, 30], min_len=120,
    ),

    # ── Корреляции (батч 3) ──
    'pearson': dict(
        module='pearson_cross_correlation', calc='calc_pearson_cross',
        entry='check_entry', exit='check_exit',
        label='Pearson', grid=[20, 30, 50], min_len=160,
    ),
    'partcorr': dict(
        module='partial_correlation_filter', calc='calc_partial_correlation',
        entry='check_entry', exit='check_exit',
        label='PartCorr', grid=[20, 30, 50], min_len=160,
    ),
    'dyncorr': dict(
        module='dynamic_correlation_regime', calc='calc_dynamic_corr',
        entry='check_entry', exit='check_exit',
        label='DynCorr', grid=[20, 30, 50], min_len=160,
    ),
    'corrbreak': dict(
        module='correlation_breakout', calc='calc_correlation_breakout',
        entry='check_entry', exit='check_exit',
        label='CorrBreak', grid=[20, 30, 50], min_len=160,
    ),
    'covbreak': dict(
        module='covariance_break', calc='calc_covariance_break',
        entry='check_entry', exit='check_exit',
        label='CovBreak', grid=[20, 30, 50], min_len=160,
    ),

    # ── Объём / прочее (батч 3) ──
    'obvslope': dict(
        module='obv_slope', calc='calc_obv_slope',
        entry='check_entry', exit='check_exit',
        label='OBVSlope', grid=[10, 20, 30], min_len=120,
    ),
    'obvema': dict(
        module='obv_ema_filter', calc='calc_obv_ema',
        entry='check_entry', exit='check_exit',
        label='OBVEMA', grid=[10, 20, 30], min_len=120,
    ),
    'cmf': dict(
        module='cmf', calc='calc_cmf',
        entry='check_entry', exit='check_exit',
        label='CMF', grid=[10, 20, 30], min_len=120,
    ),
    'adline': dict(
        module='ad_line', calc='calc_ad_line',
        entry='check_entry', exit='check_exit',
        label='ADLine', grid=[10, 20, 30], min_len=120,
    ),
    'voltrend': dict(
        module='volume_trend_confirmation', calc='calc_volume_trend',
        entry='check_entry', exit='check_exit',
        label='VolTrend', grid=[10, 20, 30], min_len=120,
    ),
    'volspike': dict(
        module='volume_spike_breakout', calc='calc_volume_spike',
        entry='check_entry', exit='check_exit',
        label='VolSpike', grid=[10, 20, 30], min_len=120,
    ),
    'heikin': dict(
        module='heikin_ashi', calc='calc_heikin_ashi',
        entry='check_entry', exit='check_exit',
        label='Heikin', grid=[10, 20], min_len=120,
    ),
    'macdrsi': dict(
        module='macd_rsi_combo', calc='calc_macd_rsi',
        entry='check_entry', exit='check_exit',
        label='MACDRSI', grid=[8, 12, 16], min_len=160,
    ),
    'emapara': dict(
        module='ema_parabolic_combo', calc='calc_ema_parabolic',
        entry='check_entry', exit='check_exit',
        label='EMAPara', grid=[10, 20, 30], min_len=200,
    ),

    # ── Ichimoku / уровни (батч 4) ──
    'ichimoku_tk': dict(
        module='ichimoku_tk_cross', calc='calc_ichimoku_tk',
        entry='check_entry', exit='check_exit',
        label='IchiTK', grid=[9, 14, 20], min_len=200,
    ),
    'ichimoku_cloud': dict(
        module='ichimoku_cloud_breakout', calc='calc_ichimoku_cloud',
        entry='check_entry', exit='check_exit',
        label='IchiCloud', grid=[20, 26, 52], min_len=200,
    ),
    'ichimoku_chikou': dict(
        module='ichimoku_chikou_filter', calc='calc_ichimoku_chikou',
        entry='check_entry', exit='check_exit',
        label='IchiChikou', grid=[9, 14, 20], min_len=200,
    ),
    'ichimoku_full': dict(
        module='ichimoku_full_system', calc='calc_ichimoku_full',
        entry='check_entry', exit='check_exit',
        label='IchiFull', grid=[9, 14, 20], min_len=200,
    ),
    'fibonacci': dict(
        module='fibonacci_retracement', calc='calc_fibonacci',
        entry='check_entry', exit='check_exit',
        label='Fib', grid=[10, 20, 50], min_len=120,
    ),
    'atrrev': dict(
        module='atr_reversion', calc='calc_atr_reversion',
        entry='check_entry', exit='check_exit',
        label='ATRRev', grid=[10, 14, 20], min_len=120,
    ),

    # ── Календарные (батч 4) ──
    'monthlyhl': dict(
        module='monthly_high_low_breakout', calc='calc_monthly_breakout',
        entry='check_entry', exit='check_exit',
        label='MonthlyHL', grid=[20, 55], min_len=120,
    ),
    'prevweek': dict(
        module='prev_week_range_breakout', calc='calc_prev_week_breakout',
        entry='check_entry', exit='check_exit',
        label='PrevWeek', grid=[5, 10, 20], min_len=120,
    ),
    'monpivot': dict(
        module='monthly_pivot_bounce', calc='calc_monthly_pivot',
        entry='check_entry', exit='check_exit',
        label='MonPivot', grid=[20, 55], min_len=120,
    ),
    'weekpivot': dict(
        module='weekly_pivot_bounce', calc='calc_weekly_pivot',
        entry='check_entry', exit='check_exit',
        label='WeekPivot', grid=[5, 20], min_len=120,
    ),
    'pivotbounce': dict(
        module='pivot_point_bounce', calc='calc_pivot_bounce',
        entry='check_entry', exit='check_exit',
        label='PivotBounce', grid=[10, 20, 55], min_len=120,
    ),
    'asianbreak': dict(
        module='asian_session_breakout', calc='calc_asian_breakout',
        entry='check_entry', exit='check_exit',
        label='AsianBreak', grid=[10, 20, 30], min_len=120,
    ),
    'firstbar': dict(
        module='first_bar_of_day', calc='calc_first_bar',
        entry='check_entry', exit='check_exit',
        label='FirstBar', grid=[10, 20, 55], min_len=120,
    ),
    'gapfill': dict(
        module='gap_fill_weekly', calc='calc_gap_fill',
        entry='check_entry', exit='check_exit',
        label='GapFill', grid=[5, 10, 20], min_len=120,
    ),
    'dowmom': dict(
        module='day_of_week_momentum', calc='calc_day_of_week',
        entry='check_entry', exit='check_exit',
        label='DoWMom', grid=[5, 10, 20], min_len=120,
    ),
    'rangedaily': dict(
        module='range_breakout_daily', calc='calc_range_breakout',
        entry='check_entry', exit='check_exit',
        label='RangeDaily', grid=[10, 20, 30], min_len=120,
    ),

    # ── Паттерны / state (батч 4) ──
    'doji': dict(
        module='doji_key_level', calc='calc_doji_key_level',
        entry='check_entry', exit='check_exit',
        label='Doji', grid=[10, 20, 50], min_len=120,
    ),
    'dbltopbot': dict(
        module='double_top_bottom', calc='calc_double_top_bottom',
        entry='check_entry', exit='check_exit',
        label='DblTopBot', grid=[10, 20, 50], min_len=120,
    ),
    'srbounce': dict(
        module='sr_bounce', calc='calc_sr_bounce',
        entry='check_entry', exit='check_exit',
        label='SRBounce', grid=[10, 20, 50], min_len=120,
    ),
    'threecrows': dict(
        module='three_crows_soldiers', calc='calc_three_crows',
        entry='check_entry', exit='check_exit',
        label='3Crows', grid=[5, 10, 20], min_len=120,
    ),
    'tweezer': dict(
        module='tweezer_top_bottom', calc='calc_tweezer',
        entry='check_entry', exit='check_exit',
        label='Tweezer', grid=[5, 10, 20], min_len=120,
    ),
    'keltatr': dict(
        module='keltner_atr_filter', calc='calc_keltner_atr',
        entry='check_entry', exit='check_exit',
        label='KeltATR', grid=[10, 20, 30], min_len=120,
    ),
    'strema': dict(
        module='supertrend_ema_filter', calc='calc_supertrend_ema',
        entry='check_entry', exit='check_exit',
        label='STrendEMA', grid=[10, 14, 20], min_len=160,
    ),
    'coinflip': dict(
        module='coin_flip_trend', calc='calc_coin_flip',
        entry='check_entry', exit='check_exit',
        label='CoinFlip', grid=[10, 20, 30], min_len=120,
    ),
    'smoothedma': dict(
        module='smoothed_ma_crossover', calc='calc_smoothed_ma',
        entry='check_entry', exit='check_exit',
        label='SmoothMA', grid=[10, 20, 30], min_len=200,
    ),
    'spearman': dict(
        module='spearman_rank_correlation', calc='calc_spearman',
        entry='check_entry', exit='check_exit',
        label='Spearman', grid=[20, 30, 50], min_len=160,
    ),
    'keltbreak': dict(
        module='keltner_breakout', calc='calc_keltner',
        entry='check_entry', exit='check_exit',
        label='KeltBreak', grid=[10, 20, 30], min_len=120,
    ),
    'atrchan': dict(
        module='atr_channel_breakout', calc='calc_atr_channel',
        entry='check_entry', exit='check_exit',
        label='ATRChan', grid=[10, 14, 20], min_len=120,
    ),
    'rsiob': dict(
        module='rsi_oversold_overbought', calc='calc_rsi',
        entry='check_entry', exit='check_exit',
        label='RSIOB', grid=[7, 14, 21], min_len=120,
    ),
    'stochastic_rsi': dict(
        module='stochastic_rsi', calc='calc_stoch_rsi',
        entry='check_entry', exit='check_exit',
        label='StochRSI', grid=[7, 14, 21], min_len=120,
    ),
    'mfi': dict(
        module='mfi_extreme', calc='calc_mfi',
        entry='check_entry', exit='check_exit',
        label='MFI', grid=[7, 14, 21], min_len=120,
    ),
    'macdzero': dict(
        module='macd_zero_cross', calc='calc_macd_zero',
        entry='check_entry', exit='check_exit',
        label='MACDZero', grid=[8, 12, 16], min_len=120,
    ),
    'rsieema': dict(
        module='rsi_ema_filter', calc='calc_rsi_ema',
        entry='check_entry', exit='check_exit',
        label='RSIEMA', grid=[7, 14, 21], min_len=160,
    ),
    'donchadx': dict(
        module='donchian_adx', calc='calc_donchian_adx',
        entry='check_entry', exit='check_exit',
        label='DonchADX', grid=[10, 20, 55], min_len=200,
    ),
    'insidebar': dict(
        module='inside_bar_breakout', calc='calc_inside_bar',
        entry='check_entry', exit='check_exit',
        label='InsideBar', grid=[5, 10, 20], min_len=120,
    ),
    'tworsi': dict(
        module='two_period_rsi', calc='calc_two_period_rsi',
        entry='check_entry', exit='check_exit',
        label='TwoRSI', grid=[7, 14, 21], min_len=120,
    ),
    'willstoch': dict(
        module='williams_stoch', calc='calc_williams_stoch',
        entry='check_entry', exit='check_exit',
        label='WillStoch', grid=[7, 14, 21], min_len=120,
    ),
    'tsi': dict(
        module='tsi', calc='calc_tsi',
        entry='check_entry', exit='check_exit',
        label='TSI', grid=[10, 14, 20], min_len=120,
    ),
    
    # ── NEW BATCH (25.10): 17 новых стратегий в 6 категориях ──
    # Mean reversion (4)
    'mr_zscore': dict(
        module='mr_zscore_reversion', calc='calc_zscore_range',
        entry='check_entry', exit='check_exit',
        label='MR-ZScore', grid=[30, 40, 60], min_len=80,
    ),
    'mr_cvd_div': dict(
        module='mr_cvd_div', calc='calc_cvd',
        entry='check_entry', exit='check_exit',
        label='MR-CVDDiv', grid=[30, 50, 80], min_len=100,
    ),
    'mr_bb_middle': dict(
        module='mr_bb_middle', calc='calc_bb_middle_z',
        entry='check_entry', exit='check_exit',
        label='MR-BBMid', grid=[20, 40, 60], min_len=70,
    ),
    'mr_rsi_sma': dict(
        module='mr_rsi_sma', calc='calc_rsi_sma_z',
        entry='check_entry', exit='check_exit',
        label='MR-RSISMA', grid=['14,50,2.0', '20,50,2.0'], min_len=100,
    ),
    # Breakout continuation (3)
    'bc_adaptive_donchian': dict(
        module='bc_adaptive_donchian', calc='calc_adaptive_donchian',
        entry='check_entry', exit='check_exit',
        label='BC-AdaptDn', grid=['10,20', '10,40'], min_len=160,
    ),
    'bc_keltner_squeeze': dict(
        module='bc_keltner_squeeze', calc='calc_keltner_squeeze',
        entry='check_entry', exit='check_exit',
        label='BC-KeltSqz', grid=[14, 20, 30], min_len=240,
    ),
    'bc_volume_confirm': dict(
        module='bc_volume_confirm', calc='calc_volume_breakout',
        entry='check_entry', exit='check_exit',
        label='BC-VolConf', grid=['20,60,80', '30,60,80'], min_len=120,
    ),
    # Reversal (3)
    'rev_liquidity_sweep': dict(
        module='rev_liquidity_sweep', calc='calc_liquidity_sweep',
        entry='check_entry', exit='check_exit',
        label='Rev-LiqSwp', grid=[10, 20, 30], min_len=50,
    ),
    'rev_swing_failure': dict(
        module='rev_swing_failure', calc='calc_swing_failure',
        entry='check_entry', exit='check_exit',
        label='Rev-SwingF', grid=['10,0.05', '10,0.10'], min_len=40,
    ),
    'rev_macd_div': dict(
        module='rev_macd_div', calc='calc_macd_divergence',
        entry='check_entry', exit='check_exit',
        label='Rev-MACDd', grid=['12,26,9', '8,17,9'], min_len=80,
    ),
    # Multi-indicator composite (3)
    'mi_rsi_bb_vol': dict(
        module='mi_rsi_bb_vol', calc='calc_rsi_bb_vol',
        entry='check_entry', exit='check_exit',
        label='MI-RSIBBVol', grid=['14,20,2.0,30', '20,20,2.0,30'], min_len=120,
    ),
    'mi_adx_rsi_ma': dict(
        module='mi_adx_rsi_ma', calc='calc_adx_rsi_ma',
        entry='check_entry', exit='check_exit',
        label='MI-ADXRSIMA', grid=['14,14,50', '20,14,50'], min_len=150,
    ),
    'mi_stoch_atr_vol': dict(
        module='mi_stoch_atr_vol', calc='calc_stoch_atr_vol',
        entry='check_entry', exit='check_exit',
        label='MI-StochAV', grid=['14,14,30', '20,14,30'], min_len=120,
    ),
    # Advanced statistical (2)
    'advstat_hurst': dict(
        module='advstat_hurst', calc='calc_hurst_exponent',
        entry='check_entry', exit='check_exit',
        label='AS-Hurst', grid=[40, 60, 100], min_len=200,
    ),
    'advstat_fractal_dim': dict(
        module='advstat_fractal_dim', calc='calc_fractal_dimension',
        entry='check_entry', exit='check_exit',
        label='AS-FractalD', grid=[14, 20, 30], min_len=120,
    ),
}

_MODULE_CACHE = {}

# ═══════════ ПОЭТАПНОЕ ВКЛЮЧЕНИЕ РЕЕСТРА В НОЧНОЙ ПЕРЕСЧЁТ ═══════════
# Включаем порциями, чтобы не получить «цунами» комбинаций разом.
# Батч 1 (15.10): 20 стратегий = 60 параметризаций на символ
#   → 60 × 3 SL × 3 TP = 540 бэктестов на символ, × 7 символов = 3780 за ночь.
# Весь реестр дал бы 240 параметризаций → 2160 на символ → 15120 за ночь.
# Добавить стратегию = дописать ключ сюда; отключить всё = оставить кортеж пустым.
ENABLED_BATCH = (
    'triple_ema', 'adx_di', 'ultimate', 'cmo', 'donchian_vol',
    'hull', 'dualema', 'macdline', 'vwmacd', 'wmaema', 'hhll', 'momthr',
    'dpo', 'ppo', 'vortex', 'elder', 'cmf', 'adline', 'heikin', 'tsi',
    # ── Батч 2 (19.10): +20 стратегий = +60 параметризаций на символ ──
    # Итого в батче 40 стратегий → 120 параметризаций × 3 SL × 3 TP = 1080
    # бэктестов на символ (× 7 символов = 7560 за ночь, вдвое к батчу 1).
    # Порядок = порядок записи в REGISTRY: MA/тренд → Bollinger/сжатие →
    # каналы/осцилляторы → корреляции → объём.
    'ema2050', 'ribbon', 'macdema', 'adxbreak', 'bbwalk', 'bbrsi', 'bbmacd', 'adxbb',
    'roc', 'forceidx', 'stochma', 'stochrsiema', 'cciext', 'pearson', 'partcorr',
    'dyncorr', 'corrbreak', 'covbreak', 'obvslope', 'obvema',
    # ── Батч 3 (19.10): остальные 41 стратегия — реестр включён на 100% ──
    # Итого 81 стратегия ≈ 240 параметризаций на символ → 240 × 3 SL × 3 TP =
    # 2160 бэктестов на символ → × 7 символов ≈ 15120 за ночь (×4 к батчу 1).
    # Если ночное окно перестанет влезать — резать здесь, а не в цикле бэктеста.
    'voltrend', 'volspike', 'macdrsi', 'emapara',
    'ichimoku_tk', 'ichimoku_cloud', 'ichimoku_chikou', 'ichimoku_full',
    'fibonacci', 'atrrev', 'monthlyhl', 'prevweek', 'monpivot', 'weekpivot',
    'pivotbounce', 'asianbreak', 'firstbar', 'gapfill', 'dowmom', 'rangedaily',
    'doji', 'dbltopbot', 'srbounce', 'threecrows', 'tweezer', 'keltatr',
    'strema', 'coinflip', 'smoothedma', 'spearman', 'keltbreak', 'atrchan',
    'rsiob', 'stochastic_rsi', 'mfi', 'macdzero', 'rsieema', 'donchadx',
    'insidebar', 'tworsi', 'willstoch',
    # ── NEW BATCH (25.10): +17 стратегий в 6 категориях ──
    # Mean reversion (4)
    'mr_zscore', 'mr_cvd_div', 'mr_bb_middle', 'mr_rsi_sma',
    # Breakout continuation (3)
    'bc_adaptive_donchian', 'bc_keltner_squeeze', 'bc_volume_confirm',
    # Reversal (3)
    'rev_liquidity_sweep', 'rev_swing_failure', 'rev_macd_div',
    # Multi-indicator composite (3)
    'mi_rsi_bb_vol', 'mi_adx_rsi_ma', 'mi_stoch_atr_vol',
    # Advanced statistical (2)
    'advstat_hurst', 'advstat_fractal_dim',
)


def _as_param(value):
    """Период из плана/JSON может прийти строкой ('14') — модули ждут число."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return float(value)
        except (TypeError, ValueError):
            return value


def enabled_keys():
    """Ключи реестра, включённые в текущий батч (только реально существующие)."""
    return tuple(k for k in ENABLED_BATCH if k in REGISTRY)


def enabled_entries():
    """[(key, entry)] включённого батча — вход generic-цикла бэктеста."""
    return [(k, REGISTRY[k]) for k in enabled_keys()]


def enabled_combos(sl_list, tp_list):
    """{type: комбинаций на символ} включённого батча — для strat_combo_map."""
    return {k: len(REGISTRY[k]['grid']) * len(sl_list) * len(tp_list) for k in enabled_keys()}


def enabled_families(sl_list, tp_list):
    """{label: (grid, sl_list, tp_list)} включённого батча — для family_fp."""
    return {REGISTRY[k]['label']: (list(REGISTRY[k]['grid']), list(sl_list), list(tp_list))
            for k in enabled_keys()}


def enabled_family_fp_items(sl_list, tp_list):
    """[(имя, (grid, sl_list, tp_list))] для family_fp — и label, и ключ.

    Два имени нужны потому, что фильтр инкрементального пересчёта (_FamilyFilter
    в functions.py) сравнивает семейства по label, а строки результатов в
    чекпойнте помечены ключом (r['type'] = ключ реестра). Если положить только
    label, кэш реестровых строк не проходит проверку 'r.type in family_fp'
    и теряется при частичном пересчёте.
    """
    items = []
    for k in enabled_keys():
        e = REGISTRY[k]
        _grids = (list(e['grid']), list(sl_list), list(tp_list))
        items.append((e['label'], _grids))
        items.append((k, _grids))
    return items


class _MissingModule:
    """Заглушка для модуля, который не импортировался.

    Любой атрибут — no-op callable, возвращающий None. Нужна, чтобы один
    битый модуль реестра не отключал live-спеки ВСЕГО реестра: calc(...)
    вернёт None, и check_active_signals корректно пропускает стратегию.
    """
    def __getattr__(self, name):
        if name == 'backtest':
            # Бэктест-слой: пусть падает исключение — его ловит _safe_backtest
            # в functions.py и отдаёт (0, 0, []), не роняя весь символ.
            raise RuntimeError(f"модуль стратегии не импортирован (нет {name})")
        return lambda *a, **k: None


def _module(name):
    """Ленивый импорт модуля стратегии с кэшем."""
    if name not in _MODULE_CACHE:
        try:
            _MODULE_CACHE[name] = importlib.import_module(f"strategies.{name}")
        except Exception as exc:
            print(f"  [WARN] стратегия '{name}' не импортируется: {exc!r} — заглушка", flush=True)
            _MODULE_CACHE[name] = _MissingModule()
    return _MODULE_CACHE[name]


def registry_backtest(key, df, param_key, sl_points, tp_points,
                      point, tick_value, tick_size, sim_lot=0.01, spread_points=0):
    """Единая точка вызова backtest(...) для любой стратегии из реестра.

    Сигнатура совпадает с контрактом standalone-стратегий:
    backtest(df, param_key, sl_points, tp_points, point, tick_value, tick_size,
             sim_lot=0.01, spread_points=0) -> (profit, n_trades, trade_profits)
    """
    entry = REGISTRY[key]
    mod = _module(entry['module'])
    return mod.backtest(df, _as_param(param_key), sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)


def build_live_specs(make_spec):
    """Собирает словарь {type: spec} для strategy_engine.check_active_signals.

    make_spec — фабрика _spec(...) из strategy_engine (передаётся снаружи,
    чтобы не тянуть туда импорт strategy_engine).

    Все стратегии реестра пишут колонку 'k'; для value-cross это непрерывная
    величина, для state — {-1,0,1}. В обоих случаях check_entry/check_exit
    принимают (prev, curr[, direction]) — сигнатура единая.
    """
    specs = {}
    for key, entry in REGISTRY.items():
        mod = _module(entry['module'])
        calc = getattr(mod, entry['calc'])
        entry_fn = getattr(mod, entry['entry'])
        exit_fn = getattr(mod, entry['exit'])
        label = entry['label']
        min_len = int(entry.get('min_len', 2))

        specs[key] = make_spec(
            # calc(df, s) — параметры берём из записи стратегии (s['param_key'])
            (lambda df, s, _c=calc: _c(df, _as_param(s['param_key']))),
            None,
            min_len,
            # snapshot: последние два значения сигнальной колонки 'k'
            (lambda df: {'prev': df['k'].iloc[-2], 'curr': df['k'].iloc[-1]}),
            (lambda v, s, d, _e=exit_fn: _e(v['prev'], v['curr'], d)),
            (lambda v, s, _e=entry_fn: _e(v['prev'], v['curr'])),
            (lambda s, _lab=label: f"{s['symbol']}, {_lab} {s.get('param_key', '')}"),
        )
    return specs


def label_for(stype):
    """Короткий ярлык семейства по типу (или None, если тип не из реестра)."""
    entry = REGISTRY.get(stype)
    return entry['label'] if entry else None


def registry_combos(sl_list, tp_list):
    """{type: число_комбинаций} — для _strategy_map / strat_combo_map."""
    return {k: len(e['grid']) * len(sl_list) * len(tp_list) for k, e in REGISTRY.items()}


def registry_families(sl_list, tp_list):
    """{label: (grid, sl_list, tp_list)} — для family_fp (фингерпринты чекпойнтов)."""
    return {e['label']: (list(e['grid']), list(sl_list), list(tp_list)) for e in REGISTRY.values()}
