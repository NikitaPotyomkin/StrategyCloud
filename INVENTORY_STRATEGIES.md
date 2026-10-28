# Инвентаризация стратегий — StrategyCloud

Дата: 2026-10-27 23:59
Источники: `strategies/*.py`, `strategies/_registry.py`, `functions.py`, `config.py`,
`journals/run.log` (прогон 27.10 20:22), `journals/ranking.txt`.

---

## 1. Итог в одну строку

**Не подключённых модулей нет.** В `strategies/` лежит **124 `.py`**:
**119 модулей стратегий** + 5 инфраструктурных (`base.py`, `_bt_core.py`,
`_calc_cache.py`, `_registry.py`, `__init__.py`). Все 119 модулей участвуют
в бэктесте, причём **двумя независимыми слоями**:

| Слой | Откуда берётся | Семейств | Параметризаций на символ | Комб./символ | Доля |
|---|---|---|---|---|---|
| **Native** — родная сетка в `functions.py` (`if test_strategy == 'xxx'`) | ручные блоки `_backtest_symbol` | 38 | — | **6 489** | 75.0 % |
| **Реестр** — `strategies/_registry.py` (`REGISTRY` + `ENABLED_BATCH`) | generic-цикл, 1 запись на стратегию | 81 | 240 | **2 160** | 25.0 % |
| **Итого** | | **119** | | **8 649** | 100 % |

`8 649 × 7 символов = 60 543` — ровно та цифра, что в логе:
`БЭКТЕСТ | 7 символов в корзине × 8649 комб. = 60543 всего`.

Проверка суммы по логу: родные семейства 6 489 (Stoch 36 … MorningStar 27) +
реестровые 2 160 (TripleEMA 36 … WeekPivot 18) = 8 649. Сходится.

---

## 2. Почему раньше казалось, что «не подключено 75»

Считалось по одному признаку — наличие ключа в `STRATEGY_COMBO_LABELS`
(`functions.py`). Там 38 родных семейств. Реестровые 81 модуля в этом словаре
отсутствуют **по замыслу**: у них нет ручного блока в `_backtest_symbol`, они
идут generic-циклом через `_registry.registry_backtest()`, а ярлык берётся из
`REGISTRY[key]['label']`. Поэтому фильтр «есть в STRATEGY_COMBO_LABELS» давал
ложный вывод «75 модулей висят без дела».

Правильная проверка — 4 признака: `REGISTRY[key]['module']`, `ENABLED_BATCH`,
`from strategies.X import` в `functions.py`, тип в `journals/active_state.json`.
Это и показывает вкладка **Roadmap**.

---

## 3. Слой Native — 38 семейств, 6 489 комб./символ

| Семейство (`type`) | Модуль | Комб./симв. |
|---|---|---|
| `ichimoku` | `ichimoku_cloud.py` | 486 |
| `parabolic` | `parabolic.py` | 450 |
| `bb_squeeze` | `bb_squeeze_breakout.py` | 405 |
| `rsi_div` | `rsi_divergence.py` | 324 |
| `percentile` | `percentile_reversion.py` | 324 |
| `bayesian` | `bayesian_trend_update.py` | 324 |
| `chi_square` | `chi_square_distribution.py` | 324 |
| `macd_histogram` | `macd_histogram_reversal.py` | 324 |
| `bollinger` | `bollinger_breakout.py` | 243 |
| `macd_cross` | `macd_cross.py` | 243 |
| `rsi_rev` | `rsi_reversal.py` | 243 |
| `sharpe` | `rolling_sharpe_filter.py` | 225 |
| `adx` | `adx_trend.py` | 225 |
| `kurtosis` | `kurtosis_spike.py` | 180 |
| `supertrend` | `supertrend.py` | 180 |
| `obv` | `obv_flow.py` | 180 |
| `runs` | `runs_test_trend.py` | 144 |
| `hurst` | `hurst_regime_filter.py` | 135 |
| `coint` | `cointegration_pairs.py` | 135 |
| `momentum` | `momentum_breakout.py` | 135 |
| `corr_momentum` | `rolling_correlation_momentum.py` | 135 |
| `rf` | `random_forest.py` | 108 |
| `logreg` | `logreg.py` | 108 |
| `zscore` | `zscore_reversion.py` | 108 |
| `lrc` | `linear_regression_channel.py` | 108 |
| `skewness` | `skewness_extreme.py` | 108 |
| `ma` | `moving_average.py` | 81 |
| `ema_cross` | `ema_crossover.py` | 81 |
| `autocorr` | `autocorrelation_momentum.py` | 81 |
| `vwap` | `vwap_reversion.py` | 81 |
| `cci` | `cci_reversion.py` | 81 |
| `stoch` | `stochastic.py` | 36 |
| `pin_bar` | `pin_bar_reversal.py` | 27 |
| `prev_daily` | `prev_daily_candle_direction.py` | 27 |
| `williams_r` | `williams_r_extreme.py` | 27 |
| `donchian` | `donchian_breakout.py` | 27 |
| `morning_star` | `morning_evening_star.py` | 27 |
| `engulfing` | `engulfing_pattern.py` | 9 |
| **Σ 38** | | **6 489** |

Сетки параметров этих семейств — в `config.py` (`StrategyParams`, константы
`*_RANGE` выше класса). SL/TP — пер-символьные (`config.SL_POINTS_GRID`),
в счёте участвует 3 × 3 = 9 пар.

---

## 4. Слой Реестр — 81 стратегия, 2 160 комб./символ

Контракт модуля: `calc_<name>(df, period) -> df['k']`, `check_entry(prev, curr)`,
`check_exit(prev, curr, direction)`, `backtest(df, param_key, sl, tp, point,
tick_value, tick_size, …)`. Включение — `ENABLED_BATCH` (включены все 81).
Комбинации = `len(grid) × 3 SL × 3 TP`.

| Ключ | Ярлык | Модуль | Сетка | N | Комб. |
|---|---|---|---|---|---|
| `triple_ema` | TripleEMA | `triple_ema` | 8,10,14,20 | 4 | 36 |
| `adx_di` | ADX-DI | `adx_di_crossover` | 7,14,21 | 3 | 27 |
| `ultimate` | UO | `ultimate_oscillator` | 7,14,21 | 3 | 27 |
| `cmo` | CMO | `cmo_extreme` | 14,20 | 2 | 18 |
| `donchian_vol` | DonchVol | `donchian_volume_filter` | 10,20,55 | 3 | 27 |
| `ema2050` | EMA2050 | `ema_crossover_20_50` | 10,20,30,50 | 4 | 36 |
| `hull` | Hull | `hull_ma_crossover` | 10,16,27,40 | 4 | 36 |
| `ribbon` | Ribbon | `ma_ribbon_expansion` | 10,20 | 2 | 18 |
| `dualema` | DualEMA | `dual_ema_slope` | 10,20,30 | 3 | 27 |
| `macdline` | MACDLine | `macd_line_crossover` | 8,12,16 | 3 | 27 |
| `macdema` | MACDEMA | `macd_ema_filter` | 8,12,16 | 3 | 27 |
| `vwmacd` | VWMACD | `vw_macd` | 8,12,16 | 3 | 27 |
| `wmaema` | WMAEMA | `wma_ema_filter` | 10,20,30 | 3 | 27 |
| `adxbreak` | ADXBreak | `adx_breakout_ema` | 7,14,21 | 3 | 27 |
| `momthr` | MomThr | `momentum_threshold` | 5,10,20 | 3 | 27 |
| `hhll` | HHLL | `hh_ll_sequence` | 5,10,20 | 3 | 27 |
| `bbwalk` | BBWalk | `bb_walk` | 10,20,30 | 3 | 27 |
| `bbrsi` | BBRsi | `bb_rsi_filter` | 10,20,30 | 3 | 27 |
| `bbmacd` | BBMacd | `bb_macd` | 10,20,30 | 3 | 27 |
| `adxbb` | ADXBB | `adx_bb_squeeze` | 7,14,21 | 3 | 27 |
| `dpo` | DPO | `dpo` | 10,20,30 | 3 | 27 |
| `ppo` | PPO | `ppo` | 10,20,30 | 3 | 27 |
| `vortex` | Vortex | `vortex_crossover` | 10,14,20 | 3 | 27 |
| `roc` | ROC | `roc_extreme` | 10,14,20 | 3 | 27 |
| `elder` | Elder | `elder_impulse` | 10,14,20 | 3 | 27 |
| `forceidx` | ForceIdx | `force_index_trend` | 10,13,20 | 3 | 27 |
| `stochma` | StochMA | `stoch_ma_filter` | 10,14,20 | 3 | 27 |
| `stochrsiema` | StochRSIEMA | `stoch_rsi_ema` | 10,14,20 | 3 | 27 |
| `cciext` | CCIExt | `cci_extreme_trend` | 14,20,30 | 3 | 27 |
| `pearson` | Pearson | `pearson_cross_correlation` | 20,30,50 | 3 | 27 |
| `partcorr` | PartCorr | `partial_correlation_filter` | 20,30,50 | 3 | 27 |
| `dyncorr` | DynCorr | `dynamic_correlation_regime` | 20,30,50 | 3 | 27 |
| `corrbreak` | CorrBreak | `correlation_breakout` | 20,30,50 | 3 | 27 |
| `covbreak` | CovBreak | `covariance_break` | 20,30,50 | 3 | 27 |
| `obvslope` | OBVSlope | `obv_slope` | 10,20,30 | 3 | 27 |
| `obvema` | OBVEMA | `obv_ema_filter` | 10,20,30 | 3 | 27 |
| `cmf` | CMF | `cmf` | 10,20,30 | 3 | 27 |
| `adline` | ADLine | `ad_line` | 10,20,30 | 3 | 27 |
| `voltrend` | VolTrend | `volume_trend_confirmation` | 10,20,30 | 3 | 27 |
| `volspike` | VolSpike | `volume_spike_breakout` | 10,20,30 | 3 | 27 |
| `heikin` | Heikin | `heikin_ashi` | 10,20 | 2 | 18 |
| `macdrsi` | MACDRSI | `macd_rsi_combo` | 8,12,16 | 3 | 27 |
| `emapara` | EMAPara | `ema_parabolic_combo` | 10,20,30 | 3 | 27 |
| `ichimoku_tk` | IchiTK | `ichimoku_tk_cross` | 9,14,20 | 3 | 27 |
| `ichimoku_cloud` | IchiCloud | `ichimoku_cloud_breakout` | 20,26,52 | 3 | 27 |
| `ichimoku_chikou` | IchiChikou | `ichimoku_chikou_filter` | 9,14,20 | 3 | 27 |
| `ichimoku_full` | IchiFull | `ichimoku_full_system` | 9,14,20 | 3 | 27 |
| `fibonacci` | Fib | `fibonacci_retracement` | 10,20,50 | 3 | 27 |
| `atrrev` | ATRRev | `atr_reversion` | 10,14,20 | 3 | 27 |
| `monthlyhl` | MonthlyHL | `monthly_high_low_breakout` | 20,55 | 2 | 18 |
| `prevweek` | PrevWeek | `prev_week_range_breakout` | 5,10,20 | 3 | 27 |
| `monpivot` | MonPivot | `monthly_pivot_bounce` | 20,55 | 2 | 18 |
| `weekpivot` | WeekPivot | `weekly_pivot_bounce` | 5,20 | 2 | 18 |
| `pivotbounce` | PivotBounce | `pivot_point_bounce` | 10,20,55 | 3 | 27 |
| `asianbreak` | AsianBreak | `asian_session_breakout` | 10,20,30 | 3 | 27 |
| `firstbar` | FirstBar | `first_bar_of_day` | 10,20,55 | 3 | 27 |
| `gapfill` | GapFill | `gap_fill_weekly` | 5,10,20 | 3 | 27 |
| `dowmom` | DoWMom | `day_of_week_momentum` | 5,10,20 | 3 | 27 |
| `rangedaily` | RangeDaily | `range_breakout_daily` | 10,20,30 | 3 | 27 |
| `doji` | Doji | `doji_key_level` | 10,20,50 | 3 | 27 |
| `dbltopbot` | DblTopBot | `double_top_bottom` | 10,20,50 | 3 | 27 |
| `srbounce` | SRBounce | `sr_bounce` | 10,20,50 | 3 | 27 |
| `threecrows` | 3Crows | `three_crows_soldiers` | 5,10,20 | 3 | 27 |
| `tweezer` | Tweezer | `tweezer_top_bottom` | 5,10,20 | 3 | 27 |
| `keltatr` | KeltATR | `keltner_atr_filter` | 10,20,30 | 3 | 27 |
| `strema` | STrendEMA | `supertrend_ema_filter` | 10,14,20 | 3 | 27 |
| `coinflip` | CoinFlip | `coin_flip_trend` | 10,20,30 | 3 | 27 |
| `smoothedma` | SmoothMA | `smoothed_ma_crossover` | 10,20,30 | 3 | 27 |
| `spearman` | Spearman | `spearman_rank_correlation` | 20,30,50 | 3 | 27 |
| `keltbreak` | KeltBreak | `keltner_breakout` | 10,20,30 | 3 | 27 |
| `atrchan` | ATRChan | `atr_channel_breakout` | 10,14,20 | 3 | 27 |
| `rsiob` | RSIOB | `rsi_oversold_overbought` | 7,14,21 | 3 | 27 |
| `stochastic_rsi` | StochRSI | `stochastic_rsi` | 7,14,21 | 3 | 27 |
| `mfi` | MFI | `mfi_extreme` | 7,14,21 | 3 | 27 |
| `macdzero` | MACDZero | `macd_zero_cross` | 8,12,16 | 3 | 27 |
| `rsieema` | RSIEMA | `rsi_ema_filter` | 7,14,21 | 3 | 27 |
| `donchadx` | DonchADX | `donchian_adx` | 10,20,55 | 3 | 27 |
| `insidebar` | InsideBar | `inside_bar_breakout` | 5,10,20 | 3 | 27 |
| `tworsi` | TwoRSI | `two_period_rsi` | 7,14,21 | 3 | 27 |
| `willstoch` | WillStoch | `williams_stoch` | 7,14,21 | 3 | 27 |
| `tsi` | TSI | `tsi` | 10,14,20 | 3 | 27 |
| **Σ 81** | | | | **240** | **2 160** |

---

## 5. Что реально ограничивает пул (а не подключение)

Лог 27.10 20:22, цифры по порядку:

```
60 543 комб. посчитано (7 × 8 649)          ← сетка целиком, включая реестр
 6 265 → точная дедупликация по (symbol, type, param_key)
   273 → t-stat ≥ 3.0 (отсеяно 5 992 из 6 265)
    25 → TP/SL + score ≥ 1.0 + probation
    22 → max_per_type = 5
    19 → торгуют (kill switch занулил AUDUSD vwap ×2 и AUDUSD cci)
```

Три вывода:

1. **Реестровые 81 стратегии считаются**, но в пул из 25 не попадают ни одной
   строкой: `ranking.txt` содержит только родные типы (`coint`, `skewness`,
   `cci`, `vwap`, `percentile`, `rf`, `macd_histogram`, `lrc`, `sharpe`,
   `bayesian`, `chi_square`, `momentum`). Причина не в «не подключено», а в
   том, что у них 3 значения параметра × 9 пар SL/TP и слабее удельный эдж —
   они проигрывают по `score`, а не отсекаются фильтром.
2. **Главный отсекатель — `min_tstat = 3.0`** при окне 30 дней (720 баров):
   на таком окне у стратегии 10–45 сделок, а t = 3.0 при WR 70 % требует n ≈ 45.
   Отсюда 273 из 6 265.
3. **`max_per_type = 5`** добивает 25 → 22 и усиливает перекос: в плане
   USDJPY coint ×4, USDCAD skewness ×4, USDCHF cci ×3.

---

## 6. Бюджет прогона

| Сценарий | Комб./символ | Всего (×7) | Время при 5.6 комб/с |
|---|---|---|---|
| Текущий (38 native + 81 реестр) | 8 649 | 60 543 | **≈ 3.0 ч** |
| Без реестра (только native) | 6 489 | 45 423 | ≈ 2.3 ч |
| Если механически удвоить сетки реестра | ~10 809 | 75 663 | ≈ 3.8 ч |

Ночное окно 03:00–10:00 = 7 ч, запас есть. Т.е. «подключать нечего» — и
бюджет комбинаций тоже не является узким местом.

---

## 7. Что делать дальше (по приоритету эффекта)

1. **Окно бэктеста 30 → 90 дней.** Снимает главный отсекатель: на 90 днях
   n растёт втрое, t-stat перестаёт резать 96 % пула. Самый сильный рычаг,
   цена — время прогона ×3 (≈ 9 ч) → нужно либо окно выходных, либо
   инкремент по барам (сейчас удалён из проекта).
2. **`_q_covered` в `main.py`** — считать по категориям, где есть стратегии
   (сейчас Σ всех 85 квот = 1.000, остаток не перераспределяется; стратегии
   занимают 9 категорий с Σq = 0.227 → используется ~23–43 % квоты).
3. **`min_tstat 3.0 → 2.5`** и/или **`max_per_type 5 → 8** — быстрые ручки,
   но лечат симптом, а не причину.
4. Реестр трогать не нужно. Если хочется поднять его долю в пуле — это
   отдельный вопрос про `score`, а не про подключение.

---

## 8. Как проверять состояние дальше

Вкладка **Roadmap** в дэшборде (файл `roadmap_tab.py`) показывает по каждому
из 119 модулей: `Standalone`, `calc_*`, `entry+exit`, `backtest`, `Реестр`,
`Батч`, `Комб./симв.`, `Native`, `Семейство`, `В плане`, `Позиция`. Фильтр
«Только пробелы» при исправном состоянии даёт пустой список — это и есть
критерий приёмки инвентаризации.
