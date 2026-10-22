"""Шаг 2 numpy-оптимизации: колоночные чтения в модулях со СВОИМ циклом.

ЧТО ДЕЛАЕТ
    В strategies/*.py у ~36 семейств бэктест написан собственной копией петли
    (не через _bt_core.run_backtest). Внутри неё те же дорогие чтения
    df['col'].iloc[i] — Python-цепочка DataFrame.__getitem__ →
    Series._iLocIndexer.__getitem__ → _ixs (~7-10 мкс на значение).

    Трансформация механическая и семантически прозрачная:
        до цикла:   _c_close = df['close'].to_numpy()          # позиционный массив
        в цикле:    df['close'].iloc[i]  →  _c_close[i]
    Позиционный доступ numpy совпадает с .iloc: и то и другое — номер строки,
    а не метка индекса. Арифметика, порядок ветвей, запись журнала не меняются.

ГРАНИЦЫ (зачем тут AST, а не regex по файлу)
    В этих же файлах есть циклы ВНУТРИ calc_* (rolling-окна, scipy). Их трогать
    нельзя: там нужны Series (dropna, .values, срезы). Поэтому область правки
    ограничена телом def backtest, найденным парсером, а не текстом файла.

ЧЕГО СКРИПТ НЕ ТРОГАЕТ (файл пропускается целиком и попадает в отчёт)
    * больше одного def backtest или их нет;
    * внутри backtest есть срезы .iloc[a:b], множественные .iloc[[...]],
      присваивание через .iloc[...] = ... (запись, а не чтение);
    * индекс бара не вида i / i±N (например i * 2, idx[i]);
    * кадр df пересоздаётся ПОСЛЕ точки вставки (массивы устарели);
    * правка уже применялась (маркер '# numpy-петля').

РЕЖИМЫ
    python tools/numpy_loop_patch.py             # отчёт, ничего не пишет
    python tools/numpy_loop_patch.py --apply     # записать (+ .bak.YYYYMMDD_HHMMSS)
    python tools/numpy_loop_patch.py --verify    # правка == ровно трансформация бэкапа
    python tools/numpy_loop_patch.py --parity    # A/B: старые модули (.bak) vs новые

ПАРИТЕТ (--parity)
    Модули из .bak подгружаются под именем strategies.<mod>__bak и подставляются
    в _registry._MODULE_CACHE и sys.modules — реестровые семейства начинают
    считать СТАРЫМ кодом. Затем все семейства плана прогоняются дважды
    (старый проход / новый проход) по всем парам SL/TP, и сравниваются profit
    (1e-6), n_trades и журнал сделок. Старые копии остаются нетронутыми.
"""
import argparse
import ast
import importlib
import importlib.machinery
import importlib.util
import os
import re
import shutil
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
STRAT = os.path.join(BASE, 'strategies')

PRELUDE_MARK = '# numpy-петля'
# индекс бара: i, i - 1, i+2 — и ничего другого (срезы и списки отсекаются)
IDX = r'(?:-?\d+|[A-Za-z_]\w*)(?:\s*[-+]\s*\d+)?'
CALL = re.compile(r"""(?P<fr>[A-Za-z_]\w*)\[\s*(?:(?P<q1>['"])(?P<c1>\w+)(?P=q1)|(?P<ci>[A-Za-z_]\w*))\s*\]"""
                  r"""\.iloc\[\s*(?P<idx>""" + IDX + r""")\s*\]""")
# присваивание через .iloc справа от которого стоит '=' (но не '==')
ASSIGN = re.compile(r'^\s*=(?!=)')
BAD_ILOC = re.compile(r'\.iloc\[\s*\[|\]\.iloc\[\s*[^\]]*:')

PARITY_TOL = 1e-6
DEFAULT_PAIRS = 9


class Skip(Exception):
    """Файл не подходит под трансформацию — причина в отчёте."""


# ═══ Трансформация ═══
def plan(text, name='?'):
    """Разобрать файл и вернуть правку, не применяя её.

    Возвращает {'first', 'cols': [(var, expr)], 'n_sub', 'new'} либо бросает Skip.
    """
    if PRELUDE_MARK in text:
        raise Skip('уже пропатчено')
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise Skip(f'не парсится: {exc}')

    fns = [n for n in ast.walk(tree)
           if isinstance(n, ast.FunctionDef)
           and (n.name == 'backtest' or n.name.startswith('backtest_'))]
    if len(fns) != 1:
        raise Skip(f'def backtest найдено: {len(fns)}')
    fn = fns[0]
    loops = [n for n in ast.walk(fn) if isinstance(n, (ast.For, ast.While))]
    if not loops:
        raise Skip('внутри backtest нет циклов')

    lines_all = text.splitlines(keepends=True)

    def _has_reads(node):
        return bool(CALL.search(''.join(lines_all[node.lineno - 1:node.end_lineno])))

    # Точка вставки — первый цикл, внутри которого реально есть наши чтения:
    # в теле бывают служебные циклы ДО подготовки (base.py: поиск колонки сигнала),
    # вставлять массивы перед ними нельзя — значения ещё не известны.
    cand = [n for n in loops if _has_reads(n)]
    if not cand:
        raise Skip('чтений df[...].iloc[i] в циклах backtest нет')
    first = min(n.lineno for n in cand)
    lines = lines_all
    head, body = lines[:first - 1], lines[first - 1:fn.end_lineno]

    # Кадр не должен пересоздаваться после точки вставки: массивы станут стухшими.
    for ln in body:
        if re.match(r'\s*df\s*=[^=]', ln) or re.match(r"\s*df\[[^\]]+\]\s*=[^=]", ln):
            raise Skip('df пересоздаётся после начала цикла')
    if body and BAD_ILOC.search('\n'.join(body)) and not CALL.search('\n'.join(body)):
        raise Skip('срезы .iloc внутри backtest без точечных чтений')
    for ln in body:
        if BAD_ILOC.search(ln):
            raise Skip('срез/список .iloc внутри backtest')

    cols = []          # [(var, expr)] в порядке первого появления
    seen = {}

    def repl(m):
        fr = m.group('fr')
        col, ident, idx = m.group('c1'), m.group('ci'), m.group('idx')
        if col:
            key = col
            expr = f"{fr}['{key}']"
            var = (f'_c_{key}' if fr == 'df' else f'_c_{fr}_{key}')
        else:
            expr = f'{fr}[{ident}]'
            var = (f'_c_{ident}' if fr == 'df' else f'_c_{fr}_{ident}')
        if var not in seen:
            seen[var] = expr
            cols.append((var, expr))
        return f'{var}[{idx}]'

    new_body, n_sub = [], 0
    for ln in body:
        # присваивание через .iloc — это запись, для неё массивы не годятся
        m = CALL.search(ln)
        if m and ASSIGN.match(ln[m.end():]):
            raise Skip('запись через .iloc[...] = внутри backtest')
        # индекс бара нестандартного вида внутри .iloc — не наш случай
        for bad in re.finditer(r'\.iloc\[\s*([^\]]*?)\s*\]', ln):
            if not re.fullmatch(IDX, bad.group(1)):
                raise Skip(f'индекс .iloc вида [{bad.group(1)}]')
        new_ln, k = CALL.subn(repl, ln)
        n_sub += k
        new_body.append(new_ln)

    if n_sub == 0:
        raise Skip('чтений df[...].iloc[i] нет')

    indent = re.match(r'\s*', body[0]).group(0)
    nl = '\r\n' if head and head[0].endswith('\r\n') else '\n'
    prelude = [f"{indent}{var} = {expr}.to_numpy()   {PRELUDE_MARK}: позиционный доступ" + nl
               for var, expr in cols]
    return {'first': first, 'cols': cols, 'n_sub': n_sub,
            'new': ''.join(head + prelude + new_body)}


def _read(path):
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read()


def _write(path, text):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def _targets():
    out = []
    for fn in sorted(os.listdir(STRAT)):
        if not fn.endswith('.py') or fn.startswith('_'):
            continue
        if fn in ('base.py',):                     # база — отдельным разбором, см. ниже
            pass
        out.append(os.path.join(STRAT, fn))
    return out


# ═══ Режим: отчёт ═══
def report(apply=False):
    done, skip = [], []
    ts = time.strftime('%Y%m%d_%H%M%S')
    for path in _targets():
        name = os.path.basename(path)[:-3]
        try:
            text = _read(path)
            p = plan(text, name)
        except Skip as exc:
            skip.append((name, str(exc)))
            continue
        except Exception as exc:                   # непредвиденное — в отчёт, не падать
            skip.append((name, f'ошибка: {exc!r}'))
            continue
        compile(p['new'], path, 'exec')
        if apply:
            shutil.copy2(path, f'{path}.bak.{ts}')
            _write(path, p['new'])
        done.append((name, p))

    hdr = f'{"модуль":<28}{"цикл":>6}{"замен":>7}{"колонок":>9}  массив'
    print(hdr)
    print('-' * (len(hdr) + 30))
    for name, p in done:
        vars_ = ', '.join(v for v, _ in p['cols'])
        print(f'{name:<28}{p["first"]:>6}{p["n_sub"]:>7}{len(p["cols"]):>9}  {vars_}')
    print('-' * (len(hdr) + 30))
    print(f'Готовы к правке: {len(done)} | пропущено: {len(skip)}'
          f'{" | ЗАПИСАНО, бэкап .bak." + ts if apply else " | режим отчёта, файлы не тронуты"}')

    if skip:
        print('\nПропущены (причина):')
        for name, why in skip:
            print(f'  {name:<28} {why}')
    return done, skip


# ═══ Режим: сверка правки с бэкапом ═══
def verify():
    bad, ok, skipped = [], 0, 0
    for path in _targets():
        name = os.path.basename(path)[:-3]
        baks = sorted(f for f in os.listdir(STRAT) if f.startswith(name + '.py.bak.'))
        if not baks:
            continue
        bak = os.path.join(STRAT, baks[-1])
        try:
            expect = plan(_read(bak), name)['new']
        except Skip as exc:
            bad.append((name, f'бэкап не трансформируется: {exc}'))
            continue
        cur = _read(path)
        if PRELUDE_MARK not in cur:            # модуль не патчился (пропущен по правилам)
            skipped += 1
            continue
        if expect == cur:
            ok += 1
        else:
            bad.append((name, 'файл отличается от трансформации бэкапа'))
    print(f'Сверено с бэкапами: совпало {ok}, расхождений {len(bad)}, не патчилось {skipped}')
    for name, why in bad:
        print(f'  {name}: {why}')
    return 0 if not bad else 1


# ═══ Режим: паритет старый vs новый ═══
def _load_bt_profile():
    path = os.path.join(BASE, 'tools', 'bt_profile.py')
    spec = importlib.util.spec_from_file_location('bt_profile_mod', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['bt_profile_mod'] = mod
    spec.loader.exec_module(mod)
    return mod


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


def _cmp(a, b, tol):
    diffs = []
    if a is None or b is None:
        return diffs if a is b else ['результат: один из прогонов отсутствует']
    if a['profit'] is None or b['profit'] is None:
        if a['profit'] is not b['profit']:
            diffs.append(f"profit {a['profit']} ≠ {b['profit']}")
    elif abs(a['profit'] - b['profit']) > tol:
        diffs.append(f"profit {a['profit']} ≠ {b['profit']}")
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


def _load_old(name, bak):
    # .bak.<ts> — не .py, поэтому spec_from_file_location вернёт spec без загрузчика
    mod_name = f'strategies.{name}__bak'
    loader = importlib.machinery.SourceFileLoader(mod_name, bak)
    spec = importlib.util.spec_from_loader(mod_name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    loader.exec_module(mod)
    return mod


def parity(symbol=None, pairs_n=0, families=None, csv=None, tol=PARITY_TOL):
    bp = _load_bt_profile()
    from config import build_default_configs
    from functions import strategy_combos_per_symbol
    import strategies._registry as reg
    from strategies._calc_cache import install as install_calc_cache, clear as calc_clear

    app = build_default_configs()
    sp = app.strategy_params
    bt = app.backtest_config
    window = bt.backtest_days * 24
    symbol = symbol or (list(bt.symbols)[0] if bt.symbols else 'GBPUSDRfd')
    df = bp.load_bars(symbol, csv).tail(window)

    sl_list, tp_list = list(sp.sl_points_list), list(sp.tp_points_list)
    pairs = [(sl, tp) for sl in sl_list for tp in tp_list]
    if pairs_n and pairs_n < len(pairs):
        step = len(pairs) / float(pairs_n)
        pairs = [pairs[int(i * step)] for i in range(pairs_n)]

    combos_map = strategy_combos_per_symbol(sp)
    fams = families or list(combos_map)
    fams = [f for f in fams if f in combos_map]

    info = None
    if not csv:
        import MetaTrader5 as mt5
        info = mt5.symbol_info(symbol)
    point = getattr(info, 'point', 0.00001) or 0.00001
    tv = getattr(info, 'trade_tick_value', 1.0) or 1.0
    ts = getattr(info, 'trade_tick_size', 0.00001) or 0.00001
    spread = getattr(info, 'spread', 10) or 0
    install_calc_cache(enabled=True, verbose=True)

    # Старые копии из бэкапов
    cache = getattr(reg, '_MODULE_CACHE', None)
    swaps = []
    for fn in sorted(os.listdir(STRAT)):
        m = re.match(r'(.+)\.py\.bak\.\d{8}_\d{6}$', fn)
        if not m:
            continue
        name = m.group(1)
        if not os.path.exists(os.path.join(STRAT, name + '.py')):
            continue
        # бэкапов у модуля бывает несколько (старые патчи) — берём самый свежий
        if fn != max(f for f in os.listdir(STRAT) if f.startswith(name + '.py.bak.')):
            continue
        old = _load_old(name, os.path.join(STRAT, fn))
        cur = importlib.import_module(f'strategies.{name}')
        swaps.append((name, cur, old))

    if not swaps:
        print('Бэкапов .bak.<ts> не найдено — A/B нечего сравнивать. Сначала --apply.')
        return 1
    print(f'Старых копий подставлено: {len(swaps)} | семейств: {len(fams)} | пар SL/TP: {len(pairs)}')

    def run(old_on):
        for name, cur, old in swaps:
            target = old if old_on else cur
            if cache is not None:
                cache[name] = target
            sys.modules[f'strategies.{name}'] = target
        out, t_ms = {}, {}
        for fam in fams:
            call, plists = bp.build_caller(fam, sp)
            if call is None or not plists:
                continue
            p = tuple(lst[0] for lst in plists)
            t0 = time.perf_counter()
            snaps = []
            for sl, tp in pairs:
                try:
                    snaps.append((sl, tp, _snapshot(
                        call(df, p, sl, tp, point, tv, ts, spread))))
                except Exception as exc:
                    snaps.append((sl, tp, {'error': repr(exc)}))
            t_ms[fam] = (time.perf_counter() - t0) * 1e3
            out[fam] = snaps
        return out, t_ms

    print('Проход 1: старые модули (.bak)…', flush=True)
    base, base_ms = run(True)
    print('Проход 2: новые модули…', flush=True)
    test, test_ms = run(False)

    bad = []
    hdr = f'{"family":<18}{"пар":>4}{"статус":>14}{"мс старый":>12}{"мс новый":>11}{"ускор.":>9}'
    print()
    print(hdr)
    print('-' * len(hdr))
    for fam in fams:
        if fam not in base:
            continue
        sb, st = base[fam], test.get(fam, [])
        if len(st) != len(sb):
            bad.append((fam, 'разное число пар'))
            continue
        diffs = []
        for (sl, tp, x), (_, _, y) in zip(sb, st):
            if isinstance(x, dict) and 'error' in x:
                if not (isinstance(y, dict) and 'error' in y):
                    diffs.append(f'{sl}/{tp}: старый упал, новый — нет')
                continue
            d = _cmp(x, y, tol)
            if d:
                diffs.append(f'{sl}/{tp}: ' + '; '.join(d))
        if diffs:
            bad.append((fam, diffs[0]))
        b_ms, t_ms = base_ms.get(fam, 0.0), test_ms.get(fam, 0.0)
        gain = (b_ms / t_ms) if t_ms > 0 else 0.0
        print(f'{fam:<18}{len(sb):>4}{("OK" if not diffs else "РАСХОЖДЕНИЕ"):>14}'
              f'{b_ms:>12.0f}{t_ms:>11.0f}{gain:>8.2f}x')

    tot_b = sum(base_ms.values())
    tot_t = sum(test_ms.values())
    print('-' * len(hdr))
    print(f'ИТОГО {len(fams) - len(bad)}/{len(fams)} семейств совпали | '
          f'{tot_b / 1000.0:.1f} с → {tot_t / 1000.0:.1f} с '
          f'({(tot_b / tot_t) if tot_t > 0 else 0:.2f}x)')
    print('Замечание: семейства, чей backtest вызывается НЕ через реестр (legacy-путь '
          'functions._backtest_*), подменой модуля не покрываются — у них сравнение '
          'идёт новый-против-нового, то есть «OK» ничего не доказывает.')
    if bad:
        print('\nРАСХОЖДЕНИЯ — модули не принимать:')
        for fam, why in bad:
            print(f'  {fam}: {why}')
        return 1
    print('\nПаритет зелёный: profit, число сделок и журнал совпали.')
    return 0


def main():
    ap = argparse.ArgumentParser(description='Numpy-петля в модулях со своим циклом')
    ap.add_argument('--apply', action='store_true', help='записать правку (+ .bak)')
    ap.add_argument('--verify', action='store_true', help='правка == трансформация бэкапа')
    ap.add_argument('--parity', action='store_true', help='A/B старые (.bak) vs новые')
    ap.add_argument('--symbol', default=None)
    ap.add_argument('--csv', default=None)
    ap.add_argument('--pairs', type=int, default=DEFAULT_PAIRS)
    ap.add_argument('--families', default=None)
    ap.add_argument('--tol', type=float, default=PARITY_TOL)
    args = ap.parse_args()

    if args.verify:
        return verify()
    if args.parity:
        fams = [f.strip() for f in args.families.split(',')] if args.families else None
        return parity(args.symbol, args.pairs, fams, args.csv, args.tol)
    report(apply=args.apply)
    return 0


if __name__ == '__main__':
    sys.exit(main())
