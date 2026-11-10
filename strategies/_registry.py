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

    # ── Догон 30.10.2026: 7 файлов, у которых вход был МЁРТВ ──
    # У них k двузначный (только ±1), а check_entry требовал prev == 0 —
    # такого состояния после прогрева не бывает, поэтому ни бэктест, ни live
    # не входили ни разу. Вход переведён на смену состояния (state_entry).
    # Стоимость: 19 параметризаций × 3 SL × 3 TP = 171 бэктест на символ.
    # grid=[34] у klinger и grid=[20] у swing_bos — в их calc период зашит
    # константой (34 / rolling(20)), другие значения дали бы тот же сигнал.
    'ma_zerolag': dict(
        module='ma_zerolag', calc='calc_ma_zerolag',
        entry='check_entry', exit='check_exit',
        label='ZeroLag', grid=[10, 16, 22, 30], min_len=120,
    ),
    'ma_frama': dict(
        module='ma_frama_slope', calc='calc_ma_frama_slope',
        entry='check_entry', exit='check_exit',
        label='FRAMA', grid=[10, 16, 22, 30], min_len=120,
    ),
    'ma_vote': dict(
        module='ma_multi_cross_vote', calc='calc_ma_multi_cross_vote',
        entry='check_entry', exit='check_exit',
        label='MAVote', grid=[5, 8, 10], min_len=240,
    ),
    'klinger': dict(
        module='osc_klinger', calc='calc_osc_klinger',
        entry='check_entry', exit='check_exit',
        label='KVO', grid=[34], min_len=120,
    ),
    'rect_break': dict(
        module='pattern_rectangle_break', calc='calc_pattern_rectangle_break',
        entry='check_entry', exit='check_exit',
        label='RectBreak', grid=[10, 20, 55], min_len=120,
    ),
    'wedge_rise': dict(
        module='pattern_wedge_rising', calc='calc_pattern_wedge_rising',
        entry='check_entry', exit='check_exit',
        label='WedgeRise', grid=[10, 20, 55], min_len=120,
    ),
    'swing_bos': dict(
        module='struct_swing_bos', calc='calc_struct_swing_bos',
        entry='check_entry', exit='check_exit',
        label='SwingBOS', grid=[20], min_len=120,
    ),


    # ═══════════ БАТЧ 4 (05.11.2026): 45 стратегий-кандидатов ═══════════
    # Написаны 29–30.10, но в реестр не попали: в Roadmap у них не было
    # колонки «Финализировано» (модуль не участвовал в ночном рэнкинге).
    # Все 45 — единый контракт: calc_<name>(df, period), check_entry,
    # check_exit, backtest. Сетка по 3 значения, 3 SL × 3 TP → 27 бэктестов
    # на стратегию на символ (45 × 27 = 1215 на символ, ×7 символов ≈ 8500
    # за ночь к прежним ~15 000). Если ночное окно перестанет влезать —
    # резать здесь, а не в цикле бэктеста (см. комментарий к ENABLED_BATCH).
    # Каналы (4)
    'chan_adaptive_donchian': dict(
        module='chan_adaptive_donchian', calc='calc_chan_adaptive_donchian',
        entry='check_entry', exit='check_exit',
        label='ch_ad', grid=[10, 20, 55], min_len=150,
    ),
    'chan_donchian_pct_squeeze': dict(
        module='chan_donchian_pct_squeeze', calc='calc_chan_donchian_pct_squeeze',
        entry='check_entry', exit='check_exit',
        label='ch_sq', grid=[20, 34, 55], min_len=150,
    ),
    'chan_median_band': dict(
        module='chan_median_band', calc='calc_chan_median_band',
        entry='check_entry', exit='check_exit',
        label='ch_med', grid=[20, 50, 100], min_len=150,
    ),
    'chan_regression_band_z': dict(
        module='chan_regression_band_z', calc='calc_chan_regression_band_z',
        entry='check_entry', exit='check_exit',
        label='ch_reg', grid=[50, 100], min_len=260,
    ),
    # Волатильность / режим волатильности (10)
    'volreg_bbw_pct_low': dict(
        module='volreg_bbw_pct_low', calc='calc_volreg_bbw_pct_low',
        entry='check_entry', exit='check_exit',
        label='vr_bbw', grid=[20, 50, 100], min_len=150,
    ),
    'volreg_choppiness': dict(
        module='volreg_choppiness', calc='calc_volreg_choppiness',
        entry='check_entry', exit='check_exit',
        label='vr_chop', grid=[14, 20, 28], min_len=150,
    ),
    'volreg_gk_zscore': dict(
        module='volreg_gk_zscore', calc='calc_volreg_gk_zscore',
        entry='check_entry', exit='check_exit',
        label='vr_gk', grid=[20, 50, 100], min_len=150,
    ),
    'volreg_nr7_break': dict(
        module='volreg_nr7_break', calc='calc_volreg_nr7_break',
        entry='check_entry', exit='check_exit',
        label='vr_nr7', grid=[7, 14, 21], min_len=120,
    ),
    'volreg_parkinson_ratio': dict(
        module='volreg_parkinson_ratio', calc='calc_volreg_parkinson_ratio',
        entry='check_entry', exit='check_exit',
        label='vr_park', grid=[14, 20, 50], min_len=150,
    ),
    'volreg_range_expansion': dict(
        module='volreg_range_expansion', calc='calc_volreg_range_expansion',
        entry='check_entry', exit='check_exit',
        label='vr_rex', grid=[5, 10, 20], min_len=120,
    ),
    'volreg_rs_break': dict(
        module='volreg_rs_break', calc='calc_volreg_rs_break',
        entry='check_entry', exit='check_exit',
        label='vr_rs', grid=[10, 20, 50], min_len=150,
    ),
    'volreg_volofvol': dict(
        module='volreg_volofvol', calc='calc_volreg_volofvol',
        entry='check_entry', exit='check_exit',
        label='vr_vov', grid=[20, 60, 120], min_len=200,
    ),
    'volreg_wr7_fade': dict(
        module='volreg_wr7_fade', calc='calc_volreg_wr7_fade',
        entry='check_entry', exit='check_exit',
        label='vr_wr7', grid=[7, 14, 21], min_len=120,
    ),
    'volreg_yz_regime': dict(
        module='volreg_yz_regime', calc='calc_volreg_yz_regime',
        entry='check_entry', exit='check_exit',
        label='vr_yz', grid=[12, 24, 48], min_len=150,
    ),
    # Профиль объёма (5)
    'volprof_cvd_div': dict(
        module='volprof_cvd_div', calc='calc_volprof_cvd_div',
        entry='check_entry', exit='check_exit',
        label='vp_cvd', grid=[20, 50, 100], min_len=150,
    ),
    'volprof_effort_result': dict(
        module='volprof_effort_result', calc='calc_volprof_effort_result',
        entry='check_entry', exit='check_exit',
        label='vp_er', grid=[10, 20, 50], min_len=150,
    ),
    'volprof_poc_break': dict(
        module='volprof_poc_break', calc='calc_volprof_poc_break',
        entry='check_entry', exit='check_exit',
        label='vp_poc', grid=[1, 5, 20], min_len=120,
    ),
    'volprof_volume_dry': dict(
        module='volprof_volume_dry', calc='calc_volprof_volume_dry',
        entry='check_entry', exit='check_exit',
        label='vp_dry', grid=[5, 10, 20], min_len=120,
    ),
    'volprof_vol_imbalance': dict(
        module='volprof_vol_imbalance', calc='calc_volprof_vol_imbalance',
        entry='check_entry', exit='check_exit',
        label='vp_imb', grid=[10, 20, 50], min_len=150,
    ),
    # Паттерны (3; rectangle_break и wedge_rising уже в реестре)
    'pattern_flag_bull': dict(
        module='pattern_flag_bull', calc='calc_pattern_flag_bull',
        entry='check_entry', exit='check_exit',
        label='pt_flag', grid=[10, 20, 40], min_len=150,
    ),
    'pattern_gap_go': dict(
        module='pattern_gap_go', calc='calc_pattern_gap_go',
        entry='check_entry', exit='check_exit',
        label='pt_gap', grid=[1, 5, 10], min_len=120,
    ),
    'pattern_triangle_sym': dict(
        module='pattern_triangle_sym', calc='calc_pattern_triangle_sym',
        entry='check_entry', exit='check_exit',
        label='pt_tri', grid=[10, 20, 40], min_len=150,
    ),
    # Осцилляторы (8; klinger уже в реестре)
    'osc_aroon': dict(
        module='osc_aroon', calc='calc_osc_aroon',
        entry='check_entry', exit='check_exit',
        label='os_aroon', grid=[14, 25, 50], min_len=150,
    ),
    'osc_bop': dict(
        module='osc_bop', calc='calc_osc_bop',
        entry='check_entry', exit='check_exit',
        label='os_bop', grid=[10, 14, 20], min_len=120,
    ),
    'osc_center_of_gravity': dict(
        module='osc_center_of_gravity', calc='calc_osc_center_of_gravity',
        entry='check_entry', exit='check_exit',
        label='os_cog', grid=[10, 14, 20], min_len=120,
    ),
    'osc_coppock': dict(
        module='osc_coppock', calc='calc_osc_coppock',
        entry='check_entry', exit='check_exit',
        label='os_copp', grid=[10, 14, 20], min_len=120,
    ),
    'osc_ehlers_stoch': dict(
        module='osc_ehlers_stoch', calc='calc_osc_ehlers_stoch',
        entry='check_entry', exit='check_exit',
        label='os_ehl', grid=[10, 14, 20], min_len=120,
    ),
    'osc_kst': dict(
        module='osc_kst', calc='calc_osc_kst',
        entry='check_entry', exit='check_exit',
        label='os_kst', grid=[9, 12, 20], min_len=120,
    ),
    'osc_mass_index': dict(
        module='osc_mass_index', calc='calc_osc_mass_index',
        entry='check_entry', exit='check_exit',
        label='os_mass', grid=[20, 25, 50], min_len=150,
    ),
    'osc_z_rsi': dict(
        module='osc_z_rsi', calc='calc_osc_z_rsi',
        entry='check_entry', exit='check_exit',
        label='os_zrsi', grid=[50, 100], min_len=200,
    ),
    # Статистика (3)
    'stat_adf_regime': dict(
        module='stat_adf_regime', calc='calc_stat_adf_regime',
        entry='check_entry', exit='check_exit',
        label='st_adf', grid=[60, 120], min_len=200,
    ),
    'stat_half_life': dict(
        module='stat_half_life', calc='calc_stat_half_life',
        entry='check_entry', exit='check_exit',
        label='st_hl', grid=[50, 100], min_len=200,
    ),
    'stat_lz_complexity': dict(
        module='stat_lz_complexity', calc='calc_stat_lz_complexity',
        entry='check_entry', exit='check_exit',
        label='st_lz', grid=[50, 100], min_len=200,
    ),
    # Режимы (3)
    'regime_er_adx_matrix': dict(
        module='regime_er_adx_matrix', calc='calc_regime_er_adx_matrix',
        entry='check_entry', exit='check_exit',
        label='rg_adx', grid=[10, 20, 40], min_len=150,
    ),
    'regime_er_low': dict(
        module='regime_er_low', calc='calc_regime_er_low',
        entry='check_entry', exit='check_exit',
        label='rg_er', grid=[10, 20, 40], min_len=150,
    ),
    'regime_vol_switch': dict(
        module='regime_vol_switch', calc='calc_regime_vol_switch',
        entry='check_entry', exit='check_exit',
        label='rg_vol', grid=[10, 20, 40], min_len=150,
    ),
    # Пары / спреды (3)
    'pair_halflife_entry': dict(
        module='pair_halflife_entry', calc='calc_pair_halflife_entry',
        entry='check_entry', exit='check_exit',
        label='pr_hl', grid=[50, 100], min_len=260,
    ),
    'pair_ratio_trend': dict(
        module='pair_ratio_trend', calc='calc_pair_ratio_trend',
        entry='check_entry', exit='check_exit',
        label='pr_ratio', grid=[10, 20, 50], min_len=150,
    ),
    'pair_spread_z_simple': dict(
        module='pair_spread_z_simple', calc='calc_pair_spread_z_simple',
        entry='check_entry', exit='check_exit',
        label='pr_z', grid=[50, 100], min_len=260,
    ),
    # Моментум (6)
    'mom_accel_z': dict(
        module='mom_accel_z', calc='calc_mom_accel_z',
        entry='check_entry', exit='check_exit',
        label='mm_accel', grid=[10, 20, 40], min_len=150,
    ),
    'mom_breakout_confirm': dict(
        module='mom_breakout_confirm', calc='calc_mom_breakout_confirm',
        entry='check_entry', exit='check_exit',
        label='mm_break', grid=[10, 20, 40], min_len=150,
    ),
    'mom_efficiency': dict(
        module='mom_efficiency', calc='calc_mom_efficiency',
        entry='check_entry', exit='check_exit',
        label='mm_eff', grid=[10, 20, 40], min_len=150,
    ),
    'mom_pullback_ratio': dict(
        module='mom_pullback_ratio', calc='calc_mom_pullback_ratio',
        entry='check_entry', exit='check_exit',
        label='mm_pull', grid=[10, 20, 40], min_len=150,
    ),
    'mom_roc_of_roc': dict(
        module='mom_roc_of_roc', calc='calc_mom_roc_of_roc',
        entry='check_entry', exit='check_exit',
        label='mm_ror', grid=[5, 10, 20], min_len=120,
    ),
    'mom_vs_vol': dict(
        module='mom_vs_vol', calc='calc_mom_vs_vol',
        entry='check_entry', exit='check_exit',
        label='mm_vol', grid=[10, 20, 40], min_len=150,
    ),

    # ═══════════ БАТЧ 6 (06.11.2026): 50 новых стратегий ═══════════
    # Волатильность (10)
    'volreg_volofvol': dict(
        module='volreg_volofvol', calc='calc_volreg_volofvol',
        entry='check_entry', exit='check_exit',
        label='vr_vov2', grid=[20, 60, 120], min_len=200,
    ),
    'volreg_ewma_accel': dict(
        module='volreg_ewma_accel', calc='calc_volreg_ewma_accel',
        entry='check_entry', exit='check_exit',
        label='vr_ewma', grid=[20, 50, 100], min_len=200,
    ),
    'volreg_intrinsic_time': dict(
        module='volreg_intrinsic_time', calc='calc_volreg_intrinsic_time',
        entry='check_entry', exit='check_exit',
        label='vr_intri', grid=[3, 5], min_len=120,
    ),
    'volreg_vhf_trend': dict(
        module='volreg_vhf_trend', calc='calc_volreg_vhf_trend',
        entry='check_entry', exit='check_exit',
        label='vr_vhf', grid=[20, 28, 40], min_len=150,
    ),
    'volreg_er_kaufman': dict(
        module='volreg_er_kaufman', calc='calc_volreg_er_kaufman',
        entry='check_entry', exit='check_exit',
        label='vr_er', grid=[10, 20], min_len=120,
    ),
    'volreg_tr_skew': dict(
        module='volreg_tr_skew', calc='calc_volreg_tr_skew',
        entry='check_entry', exit='check_exit',
        label='vr_trsk', grid=[20, 60], min_len=150,
    ),
    'volreg_yz_alt': dict(
        module='volreg_yz_regime', calc='calc_volreg_yz_regime',
        entry='check_entry', exit='check_exit',
        label='vr_yz2', grid=[12, 24], min_len=150,
    ),
    'volreg_nr7_alt': dict(
        module='volreg_nr7_break', calc='calc_volreg_nr7_break',
        entry='check_entry', exit='check_exit',
        label='vr_nr7b', grid=[7, 14], min_len=120,
    ),
    'volreg_range_exp_alt': dict(
        module='volreg_range_expansion', calc='calc_volreg_range_expansion',
        entry='check_entry', exit='check_exit',
        label='vr_rex2', grid=[5, 10], min_len=120,
    ),
    'volreg_vol_of_vol2': dict(
        module='volreg_volofvol', calc='calc_volreg_volofvol',
        entry='check_entry', exit='check_exit',
        label='vr_vov2b', grid=[60], min_len=200,
    ),
    'volreg_ewma_accel': dict(
        module='volreg_ewma_accel', calc='calc_volreg_ewma_accel',
        entry='check_entry', exit='check_exit',
        label='vr_ewma', grid=[50, 100], min_len=200,
    ),
    'volreg_intrinsic_time': dict(
        module='volreg_intrinsic_time', calc='calc_volreg_intrinsic_time',
        entry='check_entry', exit='check_exit',
        label='vr_intri', grid=[20, 40], min_len=120,
    ),
    'volreg_vhf_trend': dict(
        module='volreg_vhf_trend', calc='calc_volreg_vhf_trend',
        entry='check_entry', exit='check_exit',
        label='vr_vhf', grid=[20, 28], min_len=150,
    ),
    'volreg_er_kaufman': dict(
        module='volreg_er_kaufman', calc='calc_volreg_er_kaufman',
        entry='check_entry', exit='check_exit',
        label='vr_er', grid=[10, 20], min_len=120,
    ),
    'volreg_tr_skew': dict(
        module='volreg_tr_skew', calc='calc_volreg_tr_skew',
        entry='check_entry', exit='check_exit',
        label='vr_trsk', grid=[60], min_len=150,
    ),
    # Осцилляторы (10)
    'osc_fisher': dict(
        module='osc_fisher_transform', calc='calc_osc_fisher_transform',
        entry='check_entry', exit='check_exit',
        label='os_fish', grid=[10, 14, 20], min_len=120,
    ),
    'osc_tii': dict(
        module='osc_tii', calc='calc_osc_tii',
        entry='check_entry', exit='check_exit',
        label='os_tii', grid=[30, 60], min_len=150,
    ),
    'osc_pgo': dict(
        module='osc_pgo', calc='calc_osc_pgo',
        entry='check_entry', exit='check_exit',
        label='os_pgo', grid=[14, 20], min_len=120,
    ),
    'osc_ravi': dict(
        module='osc_ravi', calc='calc_osc_ravi',
        entry='check_entry', exit='check_exit',
        label='os_ravi', grid=['7,65', '10,50'], min_len=120,
    ),
    'osc_rvi_hlc': dict(
        module='osc_rvi_hlc', calc='calc_osc_rvi_hlc',
        entry='check_entry', exit='check_exit',
        label='os_rvi', grid=[10, 14], min_len=120,
    ),
    'osc_er_gator': dict(
        module='osc_er_gator', calc='calc_osc_er_gator',
        entry='check_entry', exit='check_exit',
        label='os_gator', grid=[20, 30], min_len=150,
    ),
    'osc_fisher_alt': dict(
        module='osc_fisher_transform', calc='calc_osc_fisher_transform',
        entry='check_entry', exit='check_exit',
        label='os_fish2', grid=[10], min_len=120,
    ),
    'osc_tii_alt': dict(
        module='osc_tii', calc='calc_osc_tii',
        entry='check_entry', exit='check_exit',
        label='os_tii2', grid=[60], min_len=150,
    ),
    'osc_pgo_alt': dict(
        module='osc_pgo', calc='calc_osc_pgo',
        entry='check_entry', exit='check_exit',
        label='os_pgo2', grid=[14], min_len=120,
    ),
    'osc_ravi_alt': dict(
        module='osc_ravi', calc='calc_osc_ravi',
        entry='check_entry', exit='check_exit',
        label='os_ravi2', grid=['7,65'], min_len=120,
    ),
    # Mean reversion (10)
    'mr_bb_atr': dict(
        module='mr_bb_atr_units', calc='calc_mr_bb_atr_units',
        entry='check_entry', exit='check_exit',
        label='mr_bba', grid=['20,2.0', '20,2.5'], min_len=120,
    ),
    'mr_median_z': dict(
        module='mr_median_z', calc='calc_mr_median_z',
        entry='check_entry', exit='check_exit',
        label='mr_medz', grid=[50, 100], min_len=150,
    ),
    'mr_dist_pct': dict(
        module='mr_distance_percentile', calc='calc_mr_distance_percentile',
        entry='check_entry', exit='check_exit',
        label='mr_dsp', grid=['20,500', '20,200'], min_len=600,
    ),
    'mr_rsi_vol': dict(
        module='mr_rsi_vol_filter', calc='calc_mr_rsi_vol_filter',
        entry='check_entry', exit='check_exit',
        label='mr_rv', grid=['14,50', '20,50'], min_len=120,
    ),
    'mr_overshoot': dict(
        module='mr_overshoot_range', calc='calc_mr_overshoot_range',
        entry='check_entry', exit='check_exit',
        label='mr_osh', grid=[20, 40], min_len=120,
    ),
    'mr_consec': dict(
        module='mr_consecutive_bars', calc='calc_mr_consecutive_bars',
        entry='check_entry', exit='check_exit',
        label='mr_con', grid=[6, 8], min_len=120,
    ),
    'mr_climax': dict(
        module='mr_climax_volume', calc='calc_mr_climax_volume',
        entry='check_entry', exit='check_exit',
        label='mr_clx', grid=[200, 100], min_len=250,
    ),
    'mr_exhaust': dict(
        module='mr_exhaustion_candle', calc='calc_mr_exhaustion_candle',
        entry='check_entry', exit='check_exit',
        label='mr_exh', grid=[20, 30], min_len=120,
    ),
    'mr_rubber': dict(
        module='mr_rubber_band', calc='calc_mr_rubber_band',
        entry='check_entry', exit='check_exit',
        label='mr_rub', grid=['20,500', '20,200'], min_len=600,
    ),
    'mr_volz': dict(
        module='mr_vol_adjusted_z', calc='calc_mr_vol_adjusted_z',
        entry='check_entry', exit='check_exit',
        label='mr_vz', grid=[100], min_len=150,
    ),
    # Статистика (10)
    'stat_vr': dict(
        module='stat_vr_ratio', calc='calc_stat_vr_ratio',
        entry='check_entry', exit='check_exit',
        label='st_vr', grid=[5, 10], min_len=200,
    ),
    'stat_ljung': dict(
        module='stat_ljung_box', calc='calc_stat_ljung_box',
        entry='check_entry', exit='check_exit',
        label='st_lj', grid=[50, 100], min_len=200,
    ),
    'stat_mutinfo': dict(
        module='stat_mutual_info', calc='calc_stat_mutual_info',
        entry='check_entry', exit='check_exit',
        label='st_mi', grid=[50, 100], min_len=200,
    ),
    'stat_ks': dict(
        module='stat_ks_change', calc='calc_stat_ks_change',
        entry='check_entry', exit='check_exit',
        label='st_ks', grid=[30, 60], min_len=200,
    ),
    'stat_hl': dict(
        module='stat_half_life', calc='calc_stat_half_life',
        entry='check_entry', exit='check_exit',
        label='st_hl2', grid=[50, 100], min_len=200,
    ),
    'stat_acf': dict(
        module='stat_autocorr_abs', calc='calc_stat_autocorr_abs',
        entry='check_entry', exit='check_exit',
        label='st_acf', grid=[100, 200], min_len=300,
    ),
    'stat_ent': dict(
        module='stat_entropy_approx', calc='calc_stat_entropy_approx',
        entry='check_entry', exit='check_exit',
        label='st_ent', grid=[50, 100], min_len=200,
    ),
    'stat_pent': dict(
        module='stat_permutation_entropy', calc='calc_stat_permutation_entropy',
        entry='check_entry', exit='check_exit',
        label='st_pe', grid=[50, 100], min_len=200,
    ),
    'stat_lz': dict(
        module='stat_lz_complexity', calc='calc_stat_lz_complexity',
        entry='check_entry', exit='check_exit',
        label='st_lz2', grid=[50, 100], min_len=200,
    ),
    'stat_ad': dict(
        module='stat_anderson_darling', calc='calc_stat_anderson_darling',
        entry='check_entry', exit='check_exit',
        label='st_ad', grid=[100, 200], min_len=300,
    ),
    # Breakout / momentum (10)
    'struct_liq_swp': dict(
        module='struct_liquidity_sweep', calc='calc_struct_liquidity_sweep',
        entry='check_entry', exit='check_exit',
        label='st_lsq', grid=[10, 20], min_len=120,
    ),
    'struct_swing': dict(
        module='struct_swing_bos', calc='calc_struct_swing_bos',
        entry='check_entry', exit='check_exit',
        label='st_swb', grid=[5, 10], min_len=120,
    ),
    'chan_dsc_sq': dict(
        module='chan_donchian_pct_squeeze', calc='calc_chan_donchian_pct_squeeze',
        entry='check_entry', exit='check_exit',
        label='ch_dsc', grid=[15, 20], min_len=150,
    ),
    'chan_regz': dict(
        module='chan_regression_band_z', calc='calc_chan_regression_band_z',
        entry='check_entry', exit='check_exit',
        label='ch_regz', grid=[50, 100], min_len=260,
    ),
    'mom_ror': dict(
        module='mom_roc_of_roc', calc='calc_mom_roc_of_roc',
        entry='check_entry', exit='check_exit',
        label='mm_ror2', grid=[5, 10], min_len=120,
    ),
    'mom_eff': dict(
        module='mom_efficiency', calc='calc_mom_efficiency',
        entry='check_entry', exit='check_exit',
        label='mm_eff2', grid=[10, 20], min_len=150,
    ),
    'mom_pull': dict(
        module='mom_pullback_ratio', calc='calc_mom_pullback_ratio',
        entry='check_entry', exit='check_exit',
        label='mm_pull2', grid=[10, 20], min_len=150,
    ),
    'pat_tri': dict(
        module='pattern_triangle_sym', calc='calc_pattern_triangle_sym',
        entry='check_entry', exit='check_exit',
        label='pt_tri2', grid=[10, 20], min_len=150,
    ),
    'pat_flag': dict(
        module='pattern_flag_bull', calc='calc_pattern_flag_bull',
        entry='check_entry', exit='check_exit',
        label='pt_flag2', grid=[10, 20], min_len=150,
    ),
    'volprof_imb': dict(
        module='volprof_vol_imbalance', calc='calc_volprof_vol_imbalance',
        entry='check_entry', exit='check_exit',
        label='vp_imb2', grid=[10, 20], min_len=150,
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
    # ── Догон 30.10.2026: 7 починенных файлов (был мёртвый вход) ──
    # +19 параметризаций на символ → +171 бэктест на символ (~+8% к ночи).
    # Пересчёт инкрементальный: family_fp знает и label, и ключ, поэтому
    # остальные семейства не трогаются.
    'ma_zerolag', 'ma_frama', 'ma_vote', 'klinger',
    'rect_break', 'wedge_rise', 'swing_bos',
    # ── Батч 5 (05.11.2026): 45 кандидатов 29–30.10 в ночной рэнкинг ──
    # Просьба: «в Roadmap не все финализированы — добавить их все». Здесь
    # именно те standalone-модули, которых не было ни в REGISTRY, ни в
    # нативной сетке functions.py. +45 стратегий ≈ +112 параметризаций на
    # символ → 112 × 3 SL × 3 TP ≈ 1000 бэктестов на символ (×7 ≈ +7000 за
    # ночь к прежним ~15 000, это ~+45% ко времени пересчёта).
    # Если ночное окно не влезает — резать этот блок, начиная с хвоста.
    'chan_adaptive_donchian', 'chan_donchian_pct_squeeze', 'chan_median_band',
    'chan_regression_band_z',
    'volreg_bbw_pct_low', 'volreg_choppiness', 'volreg_gk_zscore', 'volreg_nr7_break',
    'volreg_parkinson_ratio', 'volreg_range_expansion', 'volreg_rs_break',
    'volreg_volofvol', 'volreg_wr7_fade', 'volreg_yz_regime',
    'volprof_cvd_div', 'volprof_effort_result', 'volprof_poc_break',
    'volprof_volume_dry', 'volprof_vol_imbalance',
    'pattern_flag_bull', 'pattern_gap_go', 'pattern_triangle_sym',
    'osc_aroon', 'osc_bop', 'osc_center_of_gravity', 'osc_coppock',
    'osc_ehlers_stoch', 'osc_kst', 'osc_mass_index', 'osc_z_rsi',
    'stat_adf_regime', 'stat_half_life', 'stat_lz_complexity',
    'regime_er_adx_matrix', 'regime_er_low', 'regime_vol_switch',
    'pair_halflife_entry', 'pair_ratio_trend', 'pair_spread_z_simple',
    'mom_accel_z', 'mom_breakout_confirm', 'mom_efficiency',
    'mom_pullback_ratio', 'mom_roc_of_roc', 'mom_vs_vol',
    # ── БАТЧ 6 (06.11.2026): 55 новых стратегий в 5 категориях ──
    # Волатильность (15)
    'volreg_volofvol', 'volreg_ewma_accel', 'volreg_intrinsic_time',
    'volreg_vhf_trend', 'volreg_er_kaufman', 'volreg_tr_skew',
    'volreg_yz_alt', 'volreg_nr7_alt', 'volreg_range_exp_alt', 'volreg_vol_of_vol2',
    'volreg_ewma_accel', 'volreg_intrinsic_time', 'volreg_vhf_trend',
    'volreg_er_kaufman', 'volreg_tr_skew',
    # Осцилляторы (10)
    'osc_fisher', 'osc_tii', 'osc_pgo', 'osc_ravi', 'osc_rvi_hlc',
    'osc_er_gator', 'osc_fisher_alt', 'osc_tii_alt', 'osc_pgo_alt', 'osc_ravi_alt',
    # Mean reversion (10)
    'mr_bb_atr', 'mr_median_z', 'mr_dist_pct', 'mr_rsi_vol', 'mr_overshoot',
    'mr_consec', 'mr_climax', 'mr_exhaust', 'mr_rubber', 'mr_volz',
    # Статистика (10)
    'stat_vr', 'stat_ljung', 'stat_mutinfo', 'stat_ks', 'stat_hl',
    'stat_acf', 'stat_ent', 'stat_pent', 'stat_lz', 'stat_ad',
    # Breakout / momentum / паттерны (10)
    'struct_liq_swp', 'struct_swing', 'chan_dsc_sq', 'chan_regz',
    'mom_ror', 'mom_eff', 'mom_pull', 'pat_tri', 'pat_flag', 'volprof_imb',
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
