"""Паритет векторизации calc_* — обязателен ДО прода каждой такой правки.

ЧТО ПРОВЕРЯЕТ (две оси, обе обязательные)
    1. СТОЛБЦЫ. Расчёт вызывается дважды — старым кодом (из .bak) и новым — с
       перехватом результата. Сравниваются имена и порядок вызовов, набор колонок
       и значения: числа с допуском, bool/object — точно. Это проверяет саму
       формулу, а не только то, что она «где-то там» не изменила сигнал.
    2. РЕЗУЛЬТАТ. Тот же вызов family-бэктеста по всем парам SL/TP: profit (1e-6),
       n_trades и журнал сделок. Это проверяет, что сигналы (пороговые сравнения
       p-value/mean_ret) остались на тех же барах.

ЗАЧЕМ ОТДЕЛЬНЫЙ ИНСТРУМЕНТ
    Правка выглядит безобидно: «цикл по барам → массивы, scipy.cdf → erfc».
    Но p-value на границе 0.05 решает, войдём мы в сделку или нет, а правило
    выхода сравнивает тот же p-value с 0.2. Расхождение в 1e-12 безопасно,
    расхождение в 1e-3 — уже другая стратегия. Паритет ловит это до прода.

ОТКУДА БЕРЁТСЯ СТАРЫЙ КОД
    Из strategies/<модуль>.py.bak.<ts> (создаётся патчерами и ручными правками).
    Модуль грузится как strategies.<модуль>__bak — свои глобалы, свой код, но
    обычный пакетный контекст (относительные импорты работают).

ЗАПУСК
    python tools/calc_vector_parity.py                      # тяжёлые по calc
    python tools/calc_vector_parity.py --families chi_square
    python tools/calc_vector_parity.py --all                # все семейства плана
    python tools/calc_vector_parity.py --tol 1e-9 --pairs 9

КОД ВОЗВРАТА
    0 — колонки и результаты совпали, правку можно принимать;
    1 — расхождение: смотреть, на какой колонке/баре разъезжается.
"""
import argparse
import importlib
import importlib.machinery
import importlib.util
import inspect
import os
import re
import sys
import time

import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
STRAT = os.path.join(BASE, 'strategies')

# Семейства, у которых расчёт — O(n) питоновский цикл по барам (замер 22.10.2026).
CALC_HEAVY = ('chi_square', 'bb_squeeze', 'percentile', 'rf', 'runs', 'supertrend',
              'obv', 'kurtosis', 'hurst', 'autocorr', 'bayesian', 'cci', 'skewness',
              'coint', 'sharpe', 'lrc', 'morning_star', 'pin_bar')

PARITY_TOL = 1e-6
COL_TOL = 1e-9      # допуск по значениям колонок calc (формула, а не итог)


def _load_bt_profile():
    path = os.path.join(BASE, 'tools', 'bt_profile.py')
    spec = importlib.util.spec_from_file_location('bt_profile_mod', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['bt_profile_mod'] = mod
    spec.loader.exec_module(mod)
    return mod


def _latest_bak(name):
    """Самый свежий strategies/<name>.py.bak.<ts> (None, если бэкапа нет)."""
    baks = sorted(f for f in os.listdir(STRAT) if f.startswith(name + '.py.bak.'))
    return os.path.join(STRAT, baks[-1]) if baks else None


def _load_old(name, bak):
    """Старая копия модуля: .bak.<ts> не .py, поэтому загрузчик задаём явно."""
    mod_name = f'strategies.{name}__bak'
    loader = importlib.machinery.SourceFileLoader(mod_name, bak)
    spec = importlib.util.spec_from_loader(mod_name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    loader.exec_module(mod)
    return mod


def _module_from_caller(call):
    """Имя модуля strategies.* для legacy-семейства (нет записи в реестре).

    Все legacy-обёртки functions._backtest_* устроены одинаково:
        from strategies.<модуль> import backtest as ...
    поэтому модуль берём из исходника обёртки — таблицу соответствий не держим,
    иначе она разъедется с кодом.
    """
    try:
        src = inspect.getsource(call)
    except Exception:
        return None
    m = re.search(r'strategies\.(\w+)', src)
    return m.group(1) if m else None


_FUNCTIONS_SRC = {}


def _module_from_functions(alias):
    """Модуль strategies.* по обёртке functions._backtest_<alias>.

    Legacy-семейства идут не через реестр, а через обёртки в functions.py вида
        def _backtest_chi_square(...):
            from strategies.chi_square_distribution import backtest as ...
    Таблицу соответствий не держим (разъедется с кодом) — берём модуль из самой
    обёртки: читаем functions.py один раз и ищем имя рядом с def.
    """
    if 'src' not in _FUNCTIONS_SRC:
        with open(os.path.join(BASE, 'functions.py'), 'r', encoding='utf-8') as f:
            _FUNCTIONS_SRC['src'] = f.read()
    block = re.search(rf'def _backtest_{re.escape(alias)}\(.*?(?=\ndef |\Z)',
                      _FUNCTIONS_SRC['src'], re.S)
    if not block:
        return None
    m = re.search(r'strategies\.(\w+)', block.group(0))
    return m.group(1) if m else None


def _resolve_module(fam, entry, call, bp):
    """Имя модуля для семейства: реестр → обёртка functions → исходник вызова."""
    if entry is not None:
        return entry['module']
    return _module_from_functions(bp.ALIAS.get(fam, fam)) or _module_from_caller(call)


# ═══ Перехват результатов calc_* ═══
def _is_calc(mod, name, fn):
    return (inspect.isfunction(fn) and 'calc' in name.lower()
            and getattr(fn, '__module__', '') == mod.__name__)


def _capture(mod, call, args):
    """Выполнить call, записав (имя, результат) каждого calc_* модуля."""
    saved, recs = {}, []

    def make(fn, name):
        def wrapper(*a, **k):
            out = fn(*a, **k)                 # сначала считаем, потом фиксируем:
            recs.append((name, out))          # порядок и число вызовов сохраняются
            return out
        return wrapper

    for name in list(vars(mod)):
        fn = getattr(mod, name, None)
        if _is_calc(mod, name, fn):
            saved[name] = fn
            setattr(mod, name, make(fn, name))
    try:
        result = call(*args)
    finally:
        for name, fn in saved.items():
            setattr(mod, name, fn)
    return recs, result


def _cmp_frame(old, new, tol):
    """Расхождения между двумя кадрами (пусто = совпали)."""
    if not hasattr(old, 'columns') or not hasattr(new, 'columns'):
        return [] if old is new else ['результат calc: не DataFrame']
    diffs = []
    oc, nc = list(old.columns), list(new.columns)
    if oc != nc:
        return [f'колонки: {oc} ≠ {nc}']
    if len(old) != len(new):
        diffs.append(f'строк: {len(old)} ≠ {len(new)}')
        return diffs
    for col in oc:
        a, b = old[col], new[col]
        try:
            an = a.to_numpy()
            bn = b.to_numpy()
        except Exception:
            continue
        if an.shape != bn.shape:
            diffs.append(f'{col}: форма {an.shape} ≠ {bn.shape}')
            continue
        if an.dtype.kind in 'fiub' and bn.dtype.kind in 'fiub':
            bad = ~np.isclose(an.astype(float), bn.astype(float),
                              rtol=0.0, atol=tol, equal_nan=True)
            if bad.any():
                k = int(np.argmax(bad))
                diffs.append(f'{col}: бар #{k} {an[k]} ≠ {bn[k]}')
        else:
            if not np.array_equal(an, bn):
                k = next(i for i in range(len(an)) if an[i] != bn[i])
                diffs.append(f'{col}: объектное расхождение на баре #{k}')
    return diffs


def _snapshot(out):
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


def _cmp_result(a, b, tol):
    diffs = []
    if a is None or b is None:
        return diffs if a is b else ['результат: один из прогонов отсутствует']
    if (a['profit'] is None) != (b['profit'] is None):
        diffs.append(f"profit {a['profit']} ≠ {b['profit']}")
    elif a['profit'] is not None and abs(a['profit'] - b['profit']) > tol:
        diffs.append(f"profit {a['profit']:.6f} ≠ {b['profit']:.6f}")
    if a['n'] != b['n']:
        diffs.append(f"сделок {a['n']} ≠ {b['n']}")
    ta, tb = a['times'], b['times']
    if (ta is None) != (tb is None):
        diffs.append('журнал: есть только в одном прогоне')
    elif ta is not None:
        if len(ta) != len(tb):
            diffs.append(f'журнал: сделок {len(ta)} ≠ {len(tb)}')
        else:
            for k, (ra, rb) in enumerate(zip(ta, tb)):
                if ra[:3] != rb[:3] or abs(ra[3] - rb[3]) > tol:
                    diffs.append(f'журнал: сделка #{k} {ra} ≠ {rb}')
                    break
    return diffs


def main():
    ap = argparse.ArgumentParser(description='Паритет векторизации calc_* (старый .bak vs новый)')
    ap.add_argument('--symbol', default=None)
    ap.add_argument('--csv', default=None)
    ap.add_argument('--families', default=None, help='список семейств через запятую')
    ap.add_argument('--all', action='store_true', help='все семейства плана')
    ap.add_argument('--pairs', type=int, default=9, help='сколько пар SL/TP (0 = все)')
    ap.add_argument('--tol', type=float, default=PARITY_TOL, help='допуск по итогу')
    ap.add_argument('--col-tol', type=float, default=COL_TOL, help='допуск по значениям колонок')
    args = ap.parse_args()

    bp = _load_bt_profile()
    from config import build_default_configs
    from functions import strategy_combos_per_symbol
    import strategies._registry as reg
    from strategies._calc_cache import install as install_calc_cache

    app = build_default_configs()
    sp = app.strategy_params
    bt = app.backtest_config
    window = bt.backtest_days * 24
    symbol = args.symbol or (list(bt.symbols)[0] if bt.symbols else 'GBPUSDRfd')
    df = bp.load_bars(symbol, args.csv).tail(window)

    sl_list, tp_list = list(sp.sl_points_list), list(sp.tp_points_list)
    pairs = [(sl, tp) for sl in sl_list for tp in tp_list]
    if args.pairs and args.pairs < len(pairs):
        step = len(pairs) / float(args.pairs)
        pairs = [pairs[int(i * step)] for i in range(args.pairs)]

    combos_map = strategy_combos_per_symbol(sp)
    if args.families:
        fams = [f.strip() for f in args.families.split(',')]
    elif args.all:
        fams = list(combos_map)
    else:
        fams = [f for f in CALC_HEAVY if f in combos_map]
    if not fams:
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

    # Кэш подготовки выключен: иначе второй вызов calc не случится и сравнивать
    # будет нечего (а нам нужны КОЛОНКИ, а не только итог).
    install_calc_cache(enabled=False, verbose=False)

    cache = getattr(reg, '_MODULE_CACHE', None)

    print(f'Паритет calc | символ {symbol} | окно {window} бар | пар SL/TP: {len(pairs)} | '
          f'допуск итога {args.tol:g} / колонок {args.col_tol:g}\n')

    def run(pass_old):
        """Один проход. Возвращает ({fam: (snap, frames, мс)})."""
        out = {}
        for fam in fams:
            call, plists = bp.build_caller(fam, sp)
            entry = reg.REGISTRY.get(fam)
            mod_name = _resolve_module(fam, entry, call, bp)
            if call is None or not plists or not mod_name:
                continue
            bak = _latest_bak(mod_name)
            cur = importlib.import_module(f'strategies.{mod_name}')
            if pass_old:
                if not bak:
                    continue                  # нечего сравнивать с этим семейством
                target = _load_old(mod_name, bak)
            else:
                target = cur
            if cache is not None:
                cache[mod_name] = target
            sys.modules[f'strategies.{mod_name}'] = target

            p = tuple(lst[0] for lst in plists)
            args_ = None                   # колонки снимаются на первой паре в цикле
            t0 = time.perf_counter()
            snaps, frames = [], []
            for sl, tp in pairs:
                a = (df, p, sl, tp, point, tv, ts, spread)
                if not frames:                 # колонки снимаем на первой паре
                    frames, res = _capture(target, call, a)
                    snaps.append((sl, tp, _snapshot(res)))
                    try:
                        pass  # результат уже получен выше — calc считается один раз
                    except Exception as exc:
                        snaps.append((sl, tp, {'error': repr(exc)}))
                    continue
                try:
                    snaps.append((sl, tp, _snapshot(call(df, p, sl, tp, point, tv, ts, spread))))
                except Exception as exc:
                    snaps.append((sl, tp, {'error': repr(exc)}))
            out[fam] = (snaps, frames, (time.perf_counter() - t0) * 1e3)
            del args_
            if cache is not None:
                cache[mod_name] = cur          # вернуть живой модуль
            sys.modules[f'strategies.{mod_name}'] = cur
        return out

    print('Проход 1: старый код (.bak)…', flush=True)
    base = run(True)
    print('Проход 2: новый код…', flush=True)
    test = run(False)

    hdr = (f'{"family":<14}{"пар":>4}{"столбцы":>10}{"итог":>8}'
           f'{"мс старый":>12}{"мс новый":>11}{"ускор.":>9}')
    print()
    print(hdr)
    print('-' * len(hdr))

    bad, skipped = [], []
    for fam in fams:
        if fam not in base:
            skipped.append(fam)
            continue
        s_base, f_base, ms_base = base[fam]
        s_test, f_test, ms_test = test.get(fam, (None, None, 0.0))

        col_diffs = []
        if not f_base or not f_test:
            col_diffs = ['calc не перехвачен']
        elif len(f_base) != len(f_test):
            col_diffs = [f'вызовов calc: {len(f_base)} ≠ {len(f_test)}']
        else:
            for (n1, x), (n2, y) in zip(f_base, f_test):
                if n1 != n2:
                    col_diffs = [f'порядок calc: {n1} ≠ {n2}']
                    break
                d = _cmp_frame(x, y, args.col_tol)
                if d:
                    col_diffs = [f'{n1}: ' + '; '.join(d[:2])]
                    break

        res_diffs = []
        for (sl, tp, x), (_, _, y) in zip(s_base, s_test or []):
            if isinstance(x, dict) and 'error' in x:
                if not (isinstance(y, dict) and 'error' in y):
                    res_diffs.append(f'{sl}/{tp}: старый упал, новый — нет')
                continue
            d = _cmp_result(x, y, args.tol)
            if d:
                res_diffs.append(f'{sl}/{tp}: ' + '; '.join(d))
                break

        ok_col = not col_diffs
        ok_res = not res_diffs
        if not (ok_col and ok_res):
            bad.append((fam, (col_diffs or res_diffs)[0]))
        gain = (ms_base / ms_test) if ms_test else 0.0
        print(f'{fam:<14}{len(s_base):>4}{("OK" if ok_col else "РАСХОЖД."):>10}'
              f'{("OK" if ok_res else "РАСХОЖД."):>8}'
              f'{ms_base:>12.0f}{ms_test:>11.0f}{gain:>8.2f}x')

    print('-' * len(hdr))
    tot_b = sum(v[2] for v in base.values())
    tot_t = sum(v[2] for v in test.values())
    print(f'ИТОГО {len(fams) - len(bad) - len(skipped)}/{len(fams) - len(skipped)} совпали | '
          f'{tot_b / 1000.0:.2f} с → {tot_t / 1000.0:.2f} с '
          f'({(tot_b / tot_t) if tot_t else 0:.2f}x)')
    if skipped:
        print(f'Пропущены (нет .bak или семейства нет в плане): {", ".join(skipped)}')

    if bad:
        print('\nРАСХОЖДЕНИЯ — правку не принимать:')
        for fam, why in bad:
            print(f'  {fam}: {why}')
        print('Что делать: вернуть strategies/*.bak.<ts> на место, разобрать колонку '
              '(какой бар разошёлся) и повторить паритет.')
        return 1

    print('\nПаритет зелёный: колонки calc и итоги бэктеста совпали.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
