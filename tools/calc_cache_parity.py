"""Паритет свёртки SL/TP (strategies/_calc_cache.py) — обязателен ДО прода.

ЧТО ПРОВЕРЯЕТ
    Для каждого семейства прогоняет все пары SL/TP на одном symbol/окне несколько
    раз и сравнивает результаты:
        эталон  — кэш выключен (расчёт на каждую пару, как раньше);
        опыт    — кэш включён (подготовка 1 раз, остальные пары из кэша).
    Сравниваются profit (с допуском), n_trades (точно) и журнал сделок times
    (эпохи входа/выхода, направление, профит) — то, из чего потом строится
    чекпойнт v2 и метрики.

ЗАЧЕМ
    Кэш переиспользует подготовленный df между парами. Если семейство мутирует
    подготовленный кадр внутри своей петли, вторая пара получит испорченные
    данные. По времени это НЕ заметно — это тихая ошибка в бэктесте и в ранжировании.
    Паритет ловит её до прода.

ПОРЯДОК
    warm  — прогревочный прогон (греет внутренние кэши семейств, время не смотрим);
    эталон, опыт — рабочие прогоны, время сравнивается между ними.

ЗАПУСК
    python tools/calc_cache_parity.py                 # ~18 тяжёлых семейств (по умолчанию)
    python tools/calc_cache_parity.py --all            # все семейства плана
    python tools/calc_cache_parity.py --all --pairs 3  # быстрый смоук по 3 парам
    python tools/calc_cache_parity.py --symbol GBPUSDrfd --families chi_square,runs

КОД ВОЗВРАТА
    0 — все семейства совпали, кэш можно включать;
    1 — есть расхождения: кэш включать нельзя, провинившиеся семейства — в EXCLUDE
        (strategies/_calc_cache.py), либо calc_cache=False целиком.
"""
import argparse
import importlib.util
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

# Семейства с наибольшей долей расчёта (замер tools/bt_split.py, 22.10.2026):
# именно там кэш даёт выигрыш, и именно там петли самые большие.
HEAVY = ('chi_square', 'percentile', 'runs', 'bayesian', 'rf', 'sharpe', 'kurtosis',
         'coint', 'skewness', 'autocorr', 'bb_squeeze', 'lrc', 'hurst', 'obv',
         'supertrend', 'cci', 'pin_bar', 'morning_star')

PARITY_TOL = 1e-6


def _load_bt_profile():
    path = os.path.join(BASE, 'tools', 'bt_profile.py')
    spec = importlib.util.spec_from_file_location('bt_profile_mod', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['bt_profile_mod'] = mod
    spec.loader.exec_module(mod)
    return mod


def _snapshot(out):
    """(profit, n_trades, times) устойчиво к тому, что вернёт семейство."""
    if out is None:
        return None
    try:
        profit = float(out[0])
    except Exception:
        profit = None
    try:
        n = int(out[1])
    except Exception:
        n = None
    times = None
    if len(out) > 2:
        times = getattr(out[2], 'times', None)
        if times is not None:
            times = [list(t) for t in times]
    return {'profit': profit, 'n': n, 'times': times}


def _cmp_num(a, b, tol):
    if a is None or b is None:
        return a is b
    return abs(a - b) <= tol


def _cmp(a, b, tol):
    """Список расхождений (пусто = паритет)."""
    diffs = []
    if a is None or b is None:
        return diffs if a is b else ['результат: один из прогонов отсутствует']
    if not _cmp_num(a['profit'], b['profit'], tol):
        diffs.append(f"profit {a['profit']} ≠ {b['profit']}")
    if a['n'] != b['n']:
        diffs.append(f"сделок {a['n']} ≠ {b['n']}")
    ta, tb = a['times'], b['times']
    if (ta is None) != (tb is None):
        diffs.append('журнал сделок: есть только в одном прогоне')
    elif ta is not None:
        if len(ta) != len(tb):
            diffs.append(f'журнал: сделок {len(ta)} ≠ {len(tb)}')
        else:
            for k, (ra, rb) in enumerate(zip(ta, tb)):
                if (ra[:3] != rb[:3]) or not _cmp_num(ra[3], rb[3], tol):
                    diffs.append(f'журнал: сделка #{k} {ra} ≠ {rb}')
                    break
    return diffs


def main():
    ap = argparse.ArgumentParser(description='Паритет свёртки SL/TP (calc-cache)')
    ap.add_argument('--symbol', default=None, help='символ (по умолчанию 1-й из config)')
    ap.add_argument('--csv', default=None, help='CSV с барами (если нет терминала)')
    ap.add_argument('--families', default=None, help='список семейств через запятую')
    ap.add_argument('--all', action='store_true', help='все семейства плана (долго)')
    ap.add_argument('--pairs', type=int, default=0, help='сколько пар SL/TP (0 = все)')
    ap.add_argument('--tol', type=float, default=PARITY_TOL, help='допуск по profit')
    ap.add_argument('--no-warmup', action='store_true', help='без прогревочного прогона')
    args = ap.parse_args()

    bp = _load_bt_profile()
    from config import build_default_configs
    from functions import strategy_combos_per_symbol
    from strategies._calc_cache import install, set_enabled, clear, stats, reset_stats

    app = build_default_configs()
    sp = app.strategy_params
    bt = app.backtest_config
    window = bt.backtest_days * 24
    symbol = args.symbol or (list(bt.symbols)[0] if bt.symbols else 'GBPUSDrfd')

    print(f'Паритет свёртки SL/TP | символ {symbol} | окно {window} бар')
    df_all = bp.load_bars(symbol, args.csv)
    df = df_all.tail(window)

    sl_list = list(sp.sl_points_list)
    tp_list = list(sp.tp_points_list)
    pairs = [(sl, tp) for sl in sl_list for tp in tp_list]
    if args.pairs and args.pairs < len(pairs):
        step = len(pairs) / float(args.pairs)
        pairs = [pairs[int(i * step)] for i in range(args.pairs)]

    combos_map = strategy_combos_per_symbol(sp)
    if args.families:
        families = [f.strip() for f in args.families.split(',')]
    elif args.all:
        families = list(combos_map)
    else:
        families = [f for f in HEAVY if f in combos_map]
    if not families:
        print('Нет семейств для проверки.')
        return 1

    info = None
    if not args.csv:
        import MetaTrader5 as mt5
        info = mt5.symbol_info(symbol)
    point = getattr(info, 'point', 0.00001) or 0.00001
    tv = getattr(info, 'trade_tick_value', 1.0) or 1.0
    ts = getattr(info, 'trade_tick_size', 0.00001) or 0.00001
    spread = getattr(info, 'spread', 10) or 0

    # Обёртки ставим сразу, но с ВЫКЛЮЧЕННЫМ кэшем: эталон должен идти по тем же
    # путям вызова, что и опыт (та же обёртка, только с выключенным кэшем).
    install(enabled=False, verbose=True)

    print(f'Семейств: {len(families)} | пар SL/TP: {len(pairs)} '
          f'| прогрев: {"нет" if args.no_warmup else "да"} | допуск: {args.tol:g}\n')

    def run_pass():
        """Один проход: все пары всех семейств. Возвращает {fam: [(sl,tp,snap)]} и время."""
        out, t_ms = {}, {}
        for fam in families:
            call, plists = bp.build_caller(fam, sp)
            if call is None or not plists:
                continue
            p = tuple(lst[0] for lst in plists)
            t0 = time.perf_counter()
            snaps = []
            for sl, tp in pairs:
                try:
                    res = call(df, p, sl, tp, point, tv, ts, spread)
                    snaps.append((sl, tp, _snapshot(res)))
                except Exception as exc:
                    snaps.append((sl, tp, {'error': repr(exc)}))
            t_ms[fam] = (time.perf_counter() - t0) * 1e3
            out[fam] = snaps
        return out, t_ms

    if not args.no_warmup:
        print('Прогрев (результат не сравнивается)…', flush=True)
        run_pass()

    set_enabled(False)
    reset_stats()
    print('Эталон: кэш выключен…', flush=True)
    base, base_ms = run_pass()

    set_enabled(True)
    clear()
    reset_stats()
    print('Опыт: кэш включён…', flush=True)
    test, test_ms = run_pass()
    st = stats()

    print()
    hdr = (f'{"family":<16}{"пар":>4}{"profit":>9}{"сделки":>9}{"журнал":>9}'
           f'{"мс без":>11}{"мс с кэшем":>12}{"ускор.":>9}')
    print(hdr)
    print('-' * len(hdr))

    bad = []
    for fam in families:
        if fam not in base:
            continue
        sbase, stest = base[fam], test.get(fam, [])
        if len(stest) != len(sbase):
            bad.append((fam, 'разное число пар'))
            continue
        diffs = []
        for (sl, tp, sb), (_, _, st_) in zip(sbase, stest):
            if isinstance(sb, dict) and 'error' in sb:
                if not (isinstance(st_, dict) and 'error' in st_):
                    diffs.append(f'{sl}/{tp}: эталон упал, опыт — нет')
                continue
            d = _cmp(sb, st_, args.tol)
            if d:
                diffs.append(f'{sl}/{tp}: ' + '; '.join(d))
        ok = not diffs
        if not ok:
            bad.append((fam, diffs[0] if diffs else 'расхождение'))
        b_ms, t_ms = base_ms.get(fam, 0.0), test_ms.get(fam, 0.0)
        gain = (b_ms / t_ms) if t_ms > 0 else 0.0
        print(f'{fam:<16}{len(sbase):>4}{"OK" if ok else "РАСХОЖДЕНИЕ":>9}'
              f'{("OK" if ok else "—"):>9}{("OK" if ok else "—"):>9}'
              f'{b_ms:>11.0f}{t_ms:>12.0f}{gain:>8.2f}x')

    print('-' * len(hdr))
    tot_b = sum(base_ms.values())
    tot_t = sum(test_ms.values())
    print(f'ИТОГО {len(families) - len(bad)}/{len(families)} семейств совпали | '
          f'время {tot_b / 1000.0:.1f} с → {tot_t / 1000.0:.1f} с '
          f'({(tot_b / tot_t) if tot_t > 0 else 0:.2f}x)')
    print(f'Кэш: попаданий {st["hit"]}, промахов {st["miss"]}, '
          f'сэкономлено ~{st["sec_saved"] / 60.0:.1f} мин')

    if bad:
        print('\nРАСХОЖДЕНИЯ — кэш включать нельзя:')
        for fam, why in bad:
            print(f'  {fam}: {why}')
        print('Что делать: добавить провинившиеся функции в EXCLUDE '
              '(strategies/_calc_cache.py, полное имя вида '
              'strategies.<модуль>.<функция>) и повторить паритет, '
              'либо оставить calc_cache=False.')
        return 1

    print('\nПаритет зелёный: profit, число сделок и журнал совпали по всем парам.')
    print('Можно включать: config.BacktestConfig.calc_cache=True (по умолчанию True).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
