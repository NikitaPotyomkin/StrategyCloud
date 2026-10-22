"""Профилировщик движка бэктеста (шаг 0 перед оптимизацией).

Зачем: полный прогон — 153-231 мин на 60 543 комбинации. Прежде чем что-то
оптимизировать, надо знать, КУДА уходит время. Арифметика по прошлым прогонам
(43,6 млн бар-итераций за 36 776 CPU-с) даёт ~0,8 мс CPU на одну итерацию — это
в ~40 раз больше, чем стоит сама петля, значит доминирует подготовка (индикатор
или обучение модели), а она сейчас считается 9 раз на каждую пару SL/TP.

Что измеряет (на ОДНОМ символе, все семейства из плана):
  * мс на 1 комбо (полный путь: подготовка + проход по барам);
  * время подготовки (индикатор/модель) и стоимость бара в петле;
  * «после свёртки»: сколько будет, если подготовку считать 1 раз на 9 пар SL/TP.

Как разделяются подготовка и петля (без знания внутренностей стратегий):
  T(720 бар) = prep + 719 × t_bar
  T(120 бар) = prep + 119 × t_bar
  → t_bar = (T(720) − T(120)) / 600,  prep = T(120) − 119 × t_bar
Это линейная аппроксимация: петля линейна по числу баров, подготовка — нет.
Точность достаточная, чтобы отличить «тормозит подготовка» от «тормозит петля».

Что НЕ делает: не пишет чекпойнты, не трогает journals/ и trades.db, не ходит
в торговлю. Только читает бары из терминала (или CSV) и считает время.

Запуск (из корня проекта):
  python tools/bt_profile.py                        # 1-й символ из config, 1 параметр/семейство
  python tools/bt_profile.py --symbol EURUSDrfd --sample 2
  python tools/bt_profile.py --csv bars.csv --symbol GBPUSDrfd   # без терминала
  python tools/bt_profile.py --families stoch,percentile,logreg  # только эти

CSV формат (если нет MT5): колонки time,open,high,low,close[,volume]; time —
ISO-дата или unix-секунды.
"""
import argparse
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import numpy as np                                                    # noqa: E402
import pandas as pd                                                   # noqa: E402

# ═══ Реестр семейств: откуда брать параметры (легаси) ═══
# Ключи — как в strategy_combos_per_symbol (r['type']), значения — поля
# config.StrategyParams. Таблица проверяется ниже по числу комбинаций.
LEGACY_PARAMS = {
    'stoch': ('k_periods',),
    'parabolic': ('parabolic_steps', 'parabolic_maxs'),
    'ma': ('ma_periods',),
    'rf': ('rf_lookbacks', 'rf_nbars', 'rf_thresholds'),
    'logreg': ('logreg_lookbacks', 'logreg_nbars', 'logreg_thresholds'),
    'macd_cross': ('macd_cross_fast_list', 'macd_cross_slow_list', 'macd_cross_signal_list'),
    'rsi_rev': ('rsi_rev_period_list', 'rsi_rev_oversold_list', 'rsi_rev_overbought_list'),
    'bollinger': ('bb_period_list', 'bb_std_list', 'volume_period_list'),
    'ema_cross': ('ema_fast_list', 'ema_slow_list'),
    'rsi_div': ('rsi_div_period_list', 'rsi_div_lookback_list', 'rsi_div_threshold_list'),
    'ichimoku': ('tenkan_list', 'kijun_list', 'senkou_b_list', 'displacement_list'),
    'zscore': ('zscore_sma_period_list', 'zscore_threshold_list', 'zscore_vol_period_list'),
    'autocorr': ('autocorr_lag_list', 'autocorr_threshold_list', 'autocorr_vol_period_list'),
    'hurst': ('hurst_window_list', 'hurst_trend_threshold_list', 'hurst_vol_period_list'),
    'lrc': ('lrc_period_list', 'lrc_std_threshold_list', 'lrc_vol_period_list'),
    'percentile': ('pct_period_list', 'pct_low_list', 'pct_high_list', 'pct_vol_period_list'),
    'runs': ('runs_window_list', 'runs_threshold_list', 'runs_vol_period_list'),
    'coint': ('coint_window_list', 'coint_threshold_list', 'coint_beta_period_list'),
    'sharpe': ('sharpe_window_list', 'sharpe_threshold_list', 'sharpe_vol_period_list'),
    'skewness': ('skew_window_list', 'skew_threshold_list', 'skew_vol_period_list'),
    'bayesian': ('bayes_window_list', 'bayes_threshold_list', 'bayes_prior_list'),
    'kurtosis': ('kurt_window_list', 'kurt_threshold_list', 'kurt_vol_period_list'),
    'chi_square': ('chisq_window_list', 'chisq_entry_list', 'chisq_exit_list',
                   'chisq_vol_period_list'),
    'vwap': ('vwap_vol_period_list', 'vwap_std_mult_list'),
    'momentum': ('momentum_period_list', 'momentum_threshold_list'),
    'pin_bar': ('pin_bar_body_ratio_list',),
    'prev_daily': ('prev_daily_hold_bars_list',),
    'corr_momentum': ('corr_window_list', 'corr_threshold_list'),
    'williams_r': ('williams_r_period_list',),
    'macd_histogram': ('macd_histogram_fast_list', 'macd_histogram_slow_list',
                       'macd_histogram_signal_list'),
    'bb_squeeze': ('bb_squeeze_period_list', 'bb_squeeze_std_list', 'bb_squeeze_pct_list'),
    'donchian': ('donchian_period_list',),
    'engulfing': ('engulfing_dummy',),
    'cci': ('cci_period_list', 'cci_threshold_list'),
    'supertrend': ('supertrend_period_list', 'supertrend_multiplier_list'),
    'adx': ('adx_period_list', 'adx_threshold_list'),
    'obv': ('obv_period_list', 'obv_threshold_list'),
    'morning_star': ('morning_star_body_ratio_list',),
}

# Имя функции в functions.py не всегда равно ключу семейства.
ALIAS = {
    'rsi_rev': 'rsi_reversal',
    'ema_cross': 'ema_crossover',
    'rsi_div': 'rsi_divergence',
    'corr_momentum': 'corr',
    'morning_star': 'morning_evening_star',
}

SHORT_BARS = 120          # «короткое» окно для разделения prep/петля


def load_bars(symbol, csv_path=None):
    """H1-бары: из терминала (data_loader.load_h1) или из CSV."""
    if csv_path:
        df = pd.read_csv(csv_path)
        df.columns = [c.strip().lower() for c in df.columns]
        tcol = 'time' if 'time' in df.columns else df.columns[0]
        t = df[tcol]
        if pd.api.types.is_numeric_dtype(t):
            df[tcol] = pd.to_datetime(t, unit='s')
        else:
            df[tcol] = pd.to_datetime(t)
        return df.set_index(tcol).sort_index()
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(f'MT5 initialize не удался: {mt5.last_error()}')
    import data_loader
    df = data_loader.load_h1(symbol)
    if df is None or len(df) == 0:
        raise RuntimeError(f'нет баров для {symbol}')
    return df


def build_caller(family, sp):
    """Вернуть (call, params) — как вызвать бэктест семейства и его параметры.

    call(df, params_tuple, sl, tp, point, tick_value, tick_size, spread) -> ...
    """
    import functions

    fn = getattr(functions, f'_backtest_{ALIAS.get(family, family)}', None)
    if fn is not None and family in LEGACY_PARAMS:
        lists = [getattr(sp, f) for f in LEGACY_PARAMS[family]]

        def _call(df, p, sl, tp, point, tv, ts, spread, _fn=fn):
            return _fn(df, *p, sl, tp, point, tv, ts, spread_points=spread)
        return _call, lists

    from strategies._registry import REGISTRY, registry_backtest
    if family in REGISTRY:
        grid = list(REGISTRY[family]['grid'])
        def _call(df, p, sl, tp, point, tv, ts, spread, _fam=family):
            return registry_backtest(_fam, df, p[0], sl, tp, point, tv, ts,
                                     spread_points=spread)
        return _call, [grid]

    return None, None


def _timeit(fn, repeat):
    """Минимум из repeat замеров (минимум устойчивее среднего к шуму ОС)."""
    best = None
    for _ in range(max(1, repeat)):
        t0 = time.perf_counter()
        try:
            fn()
        except Exception:
            return None       # мало баров / прогрев — замер невозможен
        dt = time.perf_counter() - t0
        best = dt if best is None else min(best, dt)
    return best


def main():
    ap = argparse.ArgumentParser(description='Профилировщик движка бэктеста')
    ap.add_argument('--symbol', default=None, help='символ (по умолчанию 1-й из config)')
    ap.add_argument('--csv', default=None, help='CSV с барами (если нет терминала)')
    ap.add_argument('--families', default=None, help='список семейств через запятую')
    ap.add_argument('--sample', type=int, default=1, help='сколько параметров на семейство')
    ap.add_argument('--repeat', type=int, default=3, help='замеров на вызов (берём минимум)')
    ap.add_argument('--days', type=int, default=None, help='окно в днях (по умолчанию config)')
    args = ap.parse_args()

    from config import build_default_configs
    from functions import strategy_combos_per_symbol
    app = build_default_configs()
    sp = app.strategy_params
    bt = app.backtest_config
    days = args.days or bt.backtest_days
    window = days * 24
    symbol = args.symbol or (list(bt.symbols)[0] if bt.symbols else 'GBPUSDrfd')
    n_symbols = len(bt.symbols) or 1

    print(f'Символ: {symbol} | окно {window} бар ({days} дн.) | корзина {n_symbols} симв.')
    df_all = load_bars(symbol, args.csv)
    if len(df_all) < window + 2:
        print(f'  ! баров всего {len(df_all)} — меньше окна {window}; беру что есть')
        window = max(SHORT_BARS + 10, len(df_all) - 2)
    df = df_all.tail(window)
    short = df_all.tail(min(SHORT_BARS, len(df) - 1))

    sl_list = list(sp.sl_points_list)
    tp_list = list(sp.tp_points_list)
    pairs = [(sl, tp) for sl in sl_list for tp in tp_list]
    combos_map = strategy_combos_per_symbol(sp)

    info = None
    if not args.csv:
        import MetaTrader5 as mt5
        info = mt5.symbol_info(symbol)
    point = getattr(info, 'point', 0.00001) or 0.00001
    tv = getattr(info, 'trade_tick_value', 1.0) or 1.0
    ts = getattr(info, 'trade_tick_size', 0.00001) or 0.00001
    spread = getattr(info, 'spread', 10) or 0

    want = [f.strip() for f in args.families.split(',')] if args.families else None
    families = [f for f in combos_map if (not want or f in want)]

    print(f'SL×TP = {len(sl_list)}×{len(tp_list)} = {len(pairs)} пар | '
          f'параметров на семейство: {args.sample} | замеров: {args.repeat}\n')
    hdr = (f'{"family":<16}{"комб/симв":>9}{"мс/комбо":>9}{"prep мс":>9}'
           f'{"мкс/бар":>9}{"итог мин":>10}{"свёртка мин":>12}{"выигрыш":>9}')
    print(hdr)
    print('-' * len(hdr))

    rows, total_now, total_fold, skipped = [], 0.0, 0.0, []
    for fam in families:
        combos = int(combos_map.get(fam) or 0)
        if combos <= 0:
            continue
        call, plists = build_caller(fam, sp)
        if call is None or not plists:
            skipped.append(fam)
            continue
        # проверка таблицы параметров: произведение списков должно дать комб/(SL×TP)
        expect = 1
        for lst in plists:
            expect *= len(lst)
        if expect * len(pairs) != combos:
            skipped.append(f'{fam} (таблица: {expect * len(pairs)} ≠ {combos})')
            continue

        params = [tuple(lst[i] for lst in plists)
                  for i in range(min(args.sample, min(len(l) for l in plists)))]

        t_full = _timeit(lambda p=params[0]: call(df, p, pairs[0][0], pairs[0][1],
                                                  point, tv, ts, spread), args.repeat)
        t_short = _timeit(lambda p=params[0]: call(short, p, pairs[0][0], pairs[0][1],
                                                   point, tv, ts, spread), args.repeat)
        n1, n2 = len(df) - 1, len(short) - 1
        t_bar = 0.0 if (t_full is None or t_short is None) else max(0.0, (t_full - t_short) / max(1, n1 - n2))
        prep = 0.0 if t_short is None else max(0.0, t_short - n2 * t_bar)

        t_all = 0.0
        for p in params:
            for sl, tp in pairs:
                _dt = _timeit(lambda p=p, sl=sl, tp=tp: call(df, p, sl, tp,
                                                                point, tv, ts, spread),
                                 args.repeat)
                t_all += _dt or 0.0
        n_calls = len(params) * len(pairs)
        per_combo = t_all / max(1, n_calls)
        loop = t_bar * n1
        # prep — стоимость подготовки ВНУТРИ одного вызова (то есть в каждом комбо).
        # Свёртка платит её один раз на все пары SL/TP → делим на число пар.
        now_s = combos * (prep + loop)
        fold_s = combos * (prep / len(pairs) + loop)

        total_now += now_s * n_symbols
        total_fold += fold_s * n_symbols
        rows.append((fam, combos, per_combo * 1e3, prep * 1e3, t_bar * 1e6,
                     now_s * n_symbols / 60.0, fold_s * n_symbols / 60.0,
                     (now_s / fold_s) if fold_s > 0 else 1.0))

    rows.sort(key=lambda r: r[5], reverse=True)
    for fam, combos, ms, prep_ms, bar_us, now_m, fold_m, gain in rows:
        print(f'{fam:<16}{combos:>9}{ms:>9.2f}{prep_ms:>9.2f}{bar_us:>9.2f}'
              f'{now_m:>10.1f}{fold_m:>12.1f}{gain:>8.1f}x')

    print('-' * len(hdr))
    print(f'{"ИТОГО":<16}{"":>9}{"":>9}{"":>9}{"":>9}'
          f'{total_now / 60.0:>10.1f}{total_fold / 60.0:>12.1f}'
          f'{(total_now / total_fold) if total_fold > 0 else 1.0:>8.1f}x')
    print(f'\nЗамерено семейств: {len(rows)} из {len(families)}.')
    if skipped:
        print(f'Пропущены (нет параметров/функции): {", ".join(skipped[:12])}'
              + (' …' if len(skipped) > 12 else ''))
    print('\nКак читать: «итог мин» — оценка полного прогона корзины при текущем коде;'
          '\n«свёртка мин» — если подготовку (prep) считать 1 раз на пары SL/TP,'
          '\nа не на каждую. Если prep мал, а выигрыш ~1x — оптимизировать петлю,'
          '\nесли prep доминирует — делать свёртку SL/TP.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
