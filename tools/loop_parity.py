"""Паритет петли бэктеста (numpy-массивы вместо df['col'].iloc[i]) — ДО прода.

ЧТО ПРОВЕРЯЕТ
    Для каждого семейства прогоняет все пары SL/TP на одном symbol/окне дважды
    и сравнивает результаты:
        эталон — strategies/_bt_core.py::_simulate_iloc  (прежний цикл, .iloc[i]);
        опыт   — strategies/_bt_core.py::_simulate_arrays (numpy-массивы).
    Сравниваются profit (допуск 1e-6), n_trades (точно) и журнал сделок times
    (эпохи входа/выхода, направление, профит).

ЗАЧЕМ
    Меняется только способ ЧТЕНИЯ колонки. Арифметика, порядок проверок и запись
    журнала сохранены, поэтому расхождение означает, что реализация разошлась с
    исходной (например, NaN/None в сигнале, dtype-конверсия, иной порядок веток).
    Паритет ловит это до прода: чекпойнт v2 и ранжирование строятся на журнале.

ПОЧЕМУ ЭТО ВАЖНО
    Петля была 107.5 мин из 203 на корзину (tools/bt_split.py, 22.10.2026).
    Источник — не `for`, а df['col'].iloc[i]: Python-цепочка DataFrame.__getitem__
    → Series._iLocIndexer.__getitem__ → _ixs → новый объект на КАЖДОЕ значение
    (~7-10 мкс против ~50 нс у numpy-массива).

СВЁРТКА SL/TP
    Кэш расчёта (strategies/_calc_cache.py) включается на время замера: тогда
    подготовка считается 1 раз на комбинацию, и разница во времени отражает
    именно петлю, а не calc_*.

ЗАПУСК
    python tools/loop_parity.py                       # ~18 тяжёлых семейств
    python tools/loop_parity.py --all                  # все семейства плана
    python tools/loop_parity.py --all --pairs 3        # быстрый смоук по 3 парам
    python tools/loop_parity.py --symbol GBPUSDrfd --families chi_square,runs

КОД ВОЗВРАТА
    0 — все семейства совпали, numpy-петлю можно включать (numpy_loop=True);
    1 — есть расхождения: numpy_loop=False (config.py) и разбор виновника.
"""
import argparse
import importlib.util
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

# Дефолтный набор: ОБА типа семейств, чтобы отчёт сразу показал охват правки.
#   через run_backtest (петля уже numpy): ma, macdzero, emapara, obvema, vwap,
#   bollinger, doji, ichimoku_tk, covbreak, voltrend.
#   свой цикл в модуле (паритет нейтрален, пока модуль не переписан): cci,
#   percentile, chi_square, supertrend, bb_squeeze.
HEAVY = ('ma', 'macdzero', 'emapara', 'obvema', 'vwap', 'bollinger', 'doji',
         'ichimoku_tk', 'covbreak', 'voltrend', 'cci', 'percentile',
         'chi_square', 'supertrend', 'bb_squeeze')
# (--all и --families переопределяют этот набор)

PARITY_TOL = 1e-6
# Ниже этого ускорения семейство, скорее всего, ходит своим циклом (не через
# run_backtest) — тогда его правят отдельно, паритет для него ничего не покажет.
OWN_LOOP_GAIN = 1.05


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
    ap = argparse.ArgumentParser(description='Паритет петли бэктеста (numpy vs iloc)')
    ap.add_argument('--symbol', default=None, help='символ (по умолчанию 1-й из config)')
    ap.add_argument('--csv', default=None, help='CSV с барами (если нет терминала)')
    ap.add_argument('--families', default=None, help='список семейств через запятую')
    ap.add_argument('--all', action='store_true', help='все семейства плана (долго)')
    ap.add_argument('--pairs', type=int, default=0, help='сколько пар SL/TP (0 = все)')
    ap.add_argument('--tol', type=float, default=PARITY_TOL, help='допуск по profit')
    ap.add_argument('--no-warmup', action='store_true', help='без прогревочного прогона')
    ap.add_argument('--no-calc-cache', action='store_true',
                    help='не включать свёртку SL/TP (тогда время мерит calc+петлю)')
    args = ap.parse_args()

    bp = _load_bt_profile()
    from config import build_default_configs
    from functions import strategy_combos_per_symbol
    from strategies import _bt_core
    from strategies._calc_cache import install as install_calc_cache, clear as calc_clear

    app = build_default_configs()
    sp = app.strategy_params
    bt = app.backtest_config
    window = bt.backtest_days * 24
    symbol = args.symbol or (list(bt.symbols)[0] if bt.symbols else 'GBPUSDrfd')

    print(f'Паритет петли | символ {symbol} | окно {window} бар')
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

    # Свёртка SL/TP: включаем на время замера, чтобы время мерило ПЕТЛЮ, а не calc_*.
    use_cache = not args.no_calc_cache
    install_calc_cache(enabled=use_cache, verbose=True)

    # Проверка, что переключатель реально работает (иначе «паритет» бессмыслен).
    _bt_core.set_numpy_loop(False)
    if _bt_core.numpy_loop_enabled():
        print('[FAIL] не удалось выключить numpy-петлю (set_numpy_loop)')
        return 1
    _bt_core.set_numpy_loop(True)
    if not _bt_core.numpy_loop_enabled():
        print('[FAIL] не удалось включить numpy-петлю (set_numpy_loop)')
        return 1

    print(f'Семейств: {len(families)} | пар SL/TP: {len(pairs)} | '
          f'свёртка SL/TP: {"вкл" if use_cache else "выкл"} | '
          f'прогрев: {"нет" if args.no_warmup else "да"} | допуск: {args.tol:g}\n')

    def run_pass(numpy_on):
        """Один проход: все пары всех семейств. Возвращает ({fam: snaps}, {fam: мс})."""
        _bt_core.set_numpy_loop(numpy_on)
        if use_cache:
            calc_clear()
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
        run_pass(True)

    print('Эталон: iloc-петля…', flush=True)
    base, base_ms = run_pass(False)

    print('Опыт: numpy-петля…', flush=True)
    test, test_ms = run_pass(True)

    print()
    hdr = (f'{"family":<16}{"пар":>4}{"profit":>9}{"сделки":>9}{"журнал":>9}'
           f'{"мс iloc":>10}{"мс numpy":>10}{"ускор.":>9}')
    print(hdr)
    print('-' * len(hdr))

    bad, own_loop = [], []
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
        if ok and gain < OWN_LOOP_GAIN:
            own_loop.append(fam)
        print(f'{fam:<16}{len(sbase):>4}{"OK" if ok else "РАСХОЖДЕНИЕ":>9}'
              f'{("OK" if ok else "—"):>9}{("OK" if ok else "—"):>9}'
              f'{b_ms:>10.0f}{t_ms:>10.0f}{gain:>8.2f}x')

    print('-' * len(hdr))
    tot_b = sum(base_ms.values())
    tot_t = sum(test_ms.values())
    print(f'ИТОГО {len(families) - len(bad)}/{len(families)} семейств совпали | '
          f'время {tot_b / 1000.0:.1f} с → {tot_t / 1000.0:.1f} с '
          f'({(tot_b / tot_t) if tot_t > 0 else 0:.2f}x)')

    if own_loop:
        print(f'Похоже на свой цикл (ускорение < {OWN_LOOP_GAIN:g}x, '
              f'run_backtest не задействован): {", ".join(own_loop)}')
        print('  → их правят отдельным шагом (numeric-цикл внутри модуля), '
              'паритет для них пока нейтрален.')

    if bad:
        print('\nРАСХОЖДЕНИЯ — numpy-петлю включать нельзя:')
        for fam, why in bad:
            print(f'  {fam}: {why}')
        print('Что делать: оставить config.BacktestConfig.numpy_loop=False '
              '(или STRATEGYCLOUD_NUMPY_LOOP=0) и разобрать виновника.')
        return 1

    print('\nПаритет зелёный: profit, число сделок и журнал совпали по всем парам.')
    print('Можно включать: config.BacktestConfig.numpy_loop=True (по умолчанию True).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
