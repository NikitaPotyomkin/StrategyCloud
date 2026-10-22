"""Честное разделение «расчёт (calc) / петля по барам» — шаг 0b движка бэктеста.

Зачем. tools/bt_profile.py делит подготовку и петлю ДВУМЯ окнами (720 и 120 бар):
    T(n) = prep + (n-1) * t_bar
Метод не может отделить расчёт индикатора от петли, если сам расчёт линеен по
числу баров (rolling/окно — типичный случай): обе статьи уезжают в t_bar, а prep
(свободный член) выходит ≈ 0. Отсюда «выигрыш свёртки 1.0x» в отчёте — артефакт
формулы, а не факт.

Что делает. Перехватывает функции-расчёты в пакете strategies (обёртка-таймер) и
замеряет вызов бэктеста по ВСЕМ парам SL/TP, разделяя время на статьи:
    calc  — расчёт признаков (индикатор/модель/статистика);
    петля — проход по барам + служебная логика.
и оценивает выигрыш свёртки SL/TP:  gain = t_call / (t_calc/N_pairs + t_loop).

v2: меряем по всем парам, а не по одной. Цена петли зависит от плотности сделок
(на самой узкой паре их в разы больше), поэтому замер только по pairs[0] раздувал
«петлю» в 2-5 раз. Средние по парам — в тех же единицах, что «мс/комбо» в
bt_profile.py, то есть ИТОГО сопоставимо с продом.

v3: режим --deep. Общая петля _bt_core.run_backtest и собственные циклы ~18
семейств структурно идентичны (5 скалярных .iloc + машинерия сделки), но по замеру
различаются в 5-6 раз: 50-57 против 200-416 мкс/бар. --deep докапывается, на что
уходит разница: дополнительно обёртываются служебные вызовы (check_entry,
check_exit, _profit/trade_profit, trade_row, state_*) и печатается их вклад плюс
ЧИСЛО СДЕЛОК на бэктест (вызовов trade_row). Остаток после calc+служебных — это
чистая цена бара.
  ! В --deep обёртки добавляют ~1-2 мкс на вызов, а check_* вызываются на каждом
  баре, поэтому абсолютные мс в этом режиме выше; сравнивать семейства между собой
  и смотреть на структуру, а не на абсолют.

Перехват. Внутри backtest модуля вызов calc_x(...) — глобальный поиск имени в
модуле, поэтому подмена атрибута модуля видна. Вложенные расчёты (calc_x вызывает
make_features) считаются один раз: время пишется только для самого внешнего вызова.
Файлы проекта, чекпойнты и journals не меняются — только чтение баров и печать.

Запуск (из корня проекта):
  python tools/bt_split.py                        # все семейства, все пары SL/TP
  python tools/bt_split.py --deep --families vwap,bollinger,macdzero,ma
  python tools/bt_split.py --pairs 3              # быстрая прикидка (3 пары из 9)
  python tools/bt_split.py --csv bars.csv --symbol GBPUSDrfd   # без терминала
"""
import argparse
import functools
import importlib
import importlib.util
import inspect
import os
import pkgutil
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import numpy as np                                                    # noqa: E402
import pandas as pd                                                   # noqa: E402

_ACC = {}                 # 'модуль.функция' -> [сумма сек, вызовов]
_WRAPPED = set()          # id уже обёрнутых функций
_DEPTH = 0                # вложенность проб: пишем время только для внешнего вызова
_DEEP = False             # --deep: ловить ещё и служебные вызовы
PROBE_HINTS = ('calc', 'features', 'prepare', 'compute')
DEEP_NAMES = ('check_entry', 'check_exit', '_profit', 'trade_profit', 'trade_row',
              'state_entry', 'state_exit')


def _load_bt_profile():
    """bt_profile.py лежит рядом, но импортируем по пути (не как пакет tools)."""
    path = os.path.join(BASE, 'tools', 'bt_profile.py')
    spec = importlib.util.spec_from_file_location('bt_profile_mod', path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules['bt_profile_mod'] = mod
    spec.loader.exec_module(mod)
    return mod


def _is_aux(name):
    """Служебный вызов петли (не расчёт признаков)."""
    return name in DEEP_NAMES


def _is_probe_name(name):
    if name in DEEP_NAMES:
        return _DEEP
    if any(h in name.lower() for h in PROBE_HINTS):
        return True
    return False


def _wrap(mod, name, fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        global _DEPTH
        outer = _DEPTH == 0
        _DEPTH += 1
        t0 = time.perf_counter()
        try:
            return fn(*a, **kw)
        finally:
            _DEPTH -= 1
            if outer:
                slot = _ACC.setdefault(f'{mod.__name__}.{name}', [0.0, 0])
                slot[0] += time.perf_counter() - t0
                slot[1] += 1
    return wrapper


def install_calc_probes(verbose=True):
    """Обернуть таймером расчётные (и, в --deep, служебные) функции strategies."""
    global _DEEP
    import strategies
    n = 0
    for info in pkgutil.iter_modules(list(strategies.__path__)):
        name = info.name
        if name.startswith('_') and not (_DEEP and name == '_bt_core'):
            continue
        try:
            mod = importlib.import_module(f'strategies.{name}')
        except Exception:
            continue
        for attr in list(vars(mod)):
            if not _is_probe_name(attr):
                continue
            fn = getattr(mod, attr, None)
            if not inspect.isfunction(fn) or id(fn) in _WRAPPED:
                continue
            _WRAPPED.add(id(fn))
            setattr(mod, attr, _wrap(mod, attr, fn))
            n += 1
    if verbose:
        print(f'Перехвачено функций: {n}' + (' (включая служебные: --deep)' if _DEEP else ''))
    return n


def reset_acc():
    _ACC.clear()


def calc_total():
    return sum(v[0] for k, v in _ACC.items() if not _is_aux(k_suffix(k)))


def k_suffix(key):
    return key.rsplit('.', 1)[-1]


def snapshot_acc():
    return {k: list(v) for k, v in _ACC.items()}


def main():
    global _DEEP
    ap = argparse.ArgumentParser(description='calc vs петля: честный замер')
    ap.add_argument('--symbol', default=None, help='символ (по умолчанию 1-й из config)')
    ap.add_argument('--csv', default=None, help='CSV с барами (если нет терминала)')
    ap.add_argument('--families', default=None, help='список семейств через запятую')
    ap.add_argument('--pairs', type=int, default=0,
                    help='сколько пар SL/TP мерять (0 = все; меньше — быстрее, но грубее)')
    ap.add_argument('--deep', action='store_true',
                    help='дополнительно мерить служебные вызовы (check_*, trade_row, …)')
    ap.add_argument('--show-pairs', action='store_true', help='печатать время по каждой паре')
    ap.add_argument('--repeat', type=int, default=1, help='замеров на вызов (берём минимум)')
    ap.add_argument('--days', type=int, default=None, help='окно в днях (по умолчанию config)')
    ap.add_argument('--top', type=int, default=15, help='сколько функций показать')
    args = ap.parse_args()
    _DEEP = bool(args.deep)

    bp = _load_bt_profile()
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
    df_all = bp.load_bars(symbol, args.csv)
    if len(df_all) < window + 2:
        print(f'  ! баров всего {len(df_all)} — меньше окна {window}; беру что есть')
        window = max(130, len(df_all) - 2)
    df = df_all.tail(window)
    bars = len(df) - 1

    sl_list = list(sp.sl_points_list)
    tp_list = list(sp.tp_points_list)
    pairs_all = [(sl, tp) for sl in sl_list for tp in tp_list]
    n_prod_pairs = len(pairs_all)
    if args.pairs and args.pairs < n_prod_pairs:
        step = n_prod_pairs / float(args.pairs)
        measure_pairs = [pairs_all[int(i * step)] for i in range(args.pairs)]
    else:
        measure_pairs = pairs_all
    combos_map = strategy_combos_per_symbol(sp)

    info = None
    if not args.csv:
        import MetaTrader5 as mt5
        info = mt5.symbol_info(symbol)
    point = getattr(info, 'point', 0.00001) or 0.00001
    tv = getattr(info, 'trade_tick_value', 1.0) or 1.0
    ts = getattr(info, 'trade_tick_size', 0.00001) or 0.00001
    spread = getattr(info, 'spread', 10) or 0

    # ВАЖНО: пробы ставим ПОСЛЕ импорта functions/config — strategy-модули к этому
    # моменту уже в sys.modules, и setattr ложится на живые объекты модулей.
    install_calc_probes()

    want = [f.strip() for f in args.families.split(',')] if args.families else None
    families = [f for f in combos_map if (not want or f in want)]

    print(f'SL×TP = {len(sl_list)}×{len(tp_list)} = {n_prod_pairs} пар; '
          f'меряю {len(measure_pairs)}, замеров на пару: {args.repeat}\n')
    hdr = (f'{"family":<16}{"комб/симв":>9}{"мс/вызов":>10}{"calc мс":>9}{"calc %":>8}'
           f'{"петля мс":>9}{"петля мкс/бар":>14}{"свёртка":>9}{("служ мс" if _DEEP else ""):>9}')
    print(hdr)
    print('-' * len(hdr))

    rows, by_calc, by_aux = [], {}, {}
    total_now = total_calc = total_loop = 0.0
    skipped = []
    for fam in families:
        combos = int(combos_map.get(fam) or 0)
        if combos <= 0:
            continue
        call, plists = bp.build_caller(fam, sp)
        if call is None or not plists:
            skipped.append(fam)
            continue
        p = tuple(lst[0] for lst in plists)
        try:
            reset_acc()
            call(df, p, measure_pairs[0][0], measure_pairs[0][1],
                 point, tv, ts, spread)                                    # прогрев
        except Exception:
            skipped.append(fam)
            continue

        t_sum, calc_sum, aux_sum, fam_calc, fam_aux, per_pair = 0.0, 0.0, 0.0, {}, {}, []
        for sl, tp in measure_pairs:
            best, best_snap = None, {}
            for _ in range(max(1, args.repeat)):
                reset_acc()
                t0 = time.perf_counter()
                try:
                    call(df, p, sl, tp, point, tv, ts, spread)
                except Exception:
                    best = None
                    break
                dt = time.perf_counter() - t0
                if best is None or dt < best:
                    best, best_snap = dt, snapshot_acc()
            if best is None:
                continue
            best_calc = sum(v[0] for k, v in best_snap.items() if not _is_aux(k_suffix(k)))
            t_sum += best
            calc_sum += best_calc
            aux_sum += sum(v[0] for k, v in best_snap.items() if _is_aux(k_suffix(k)))
            per_pair.append((sl, tp, best, best_calc))
            for k, v in best_snap.items():
                store = fam_aux if _is_aux(k_suffix(k)) else fam_calc
                slot = store.setdefault(k, [0.0, 0])
                slot[0] += v[0]
                slot[1] += v[1]
        n_meas = len(per_pair)
        if n_meas == 0:
            skipped.append(fam)
            continue

        ms_call = t_sum / n_meas * 1e3          # среднее по парам, как «мс/комбо» в bt_profile
        ms_calc = calc_sum / n_meas * 1e3
        ms_aux = aux_sum / n_meas * 1e3
        ms_loop = max(0.0, ms_call - ms_calc - ms_aux)
        loop_us_bar = ms_loop * 1e3 / max(1, bars)
        gain = ms_call / (ms_calc / n_prod_pairs + ms_loop) if ms_loop > 0 else 1.0
        now_s = combos * (ms_call / 1e3) * n_symbols
        total_now += now_s
        total_calc += combos * (ms_calc / 1e3) * n_symbols
        total_loop += combos * (ms_loop + ms_aux) / 1e3 * n_symbols
        for k, v in fam_calc.items():
            by_calc[k] = by_calc.get(k, 0.0) + combos * (v[0] / n_meas) * n_symbols
        for k, v in fam_aux.items():
            by_aux[k] = by_aux.get(k, 0.0) + combos * (v[0] / n_meas) * n_symbols
        trades = max([v[1] for k, v in fam_aux.items() if _is_aux(k_suffix(k))] or [0]) / n_meas
        rows.append((fam, combos, ms_call, ms_calc, ms_aux, ms_loop, loop_us_bar, gain,
                     now_s / 60.0, trades))
        if args.show_pairs:
            detail = ', '.join(f'{sl}/{tp}:{t * 1e3:.0f}мс(c{cm * 1e3:.0f})'
                               for sl, tp, t, cm in per_pair)
            print(f'  {fam:<14} {detail}')

    rows.sort(key=lambda r: r[8], reverse=True)
    for fam, combos, ms, calc_ms, aux_ms, loop_ms, loop_us, gain, now_m, trades in rows:
        extra = f'{aux_ms:>9.2f}' if _DEEP else ''
        tail = f' сдел: {trades:.0f}' if _DEEP else ''
        print(f'{fam:<16}{combos:>9}{ms:>10.2f}{calc_ms:>9.2f}'
              f'{100.0 * calc_ms / ms if ms > 0 else 0.0:>7.0f}%'
              f'{loop_ms:>9.2f}{loop_us:>14.1f}{gain:>8.1f}x{extra}{tail}')

    print('-' * len(hdr))
    fold_s = total_calc / n_prod_pairs + total_loop
    print(f'{"ИТОГО мин":<16}{"":>9}{total_now / 60.0:>10.1f}'
          f'{total_calc / 60.0:>9.1f}{100.0 * total_calc / max(1e-9, total_now):>7.0f}%'
          f'{total_loop / 60.0:>9.1f}{"":>14}{total_now / max(1e-9, fold_s):>8.1f}x')
    print(f'\nЗамерено семейств: {len(rows)} из {len(families)}.')
    if skipped:
        print(f'Пропущены: {", ".join(skipped[:14])}' + (' …' if len(skipped) > 14 else ''))

    if by_calc:
        print(f'\nТоп-{args.top} расчётных функций по вкладу в полный прогон корзины:')
        for k, v in sorted(by_calc.items(), key=lambda kv: kv[1], reverse=True)[:args.top]:
            print(f'  {v / 60.0:>8.1f} мин  {k}')
    if _DEEP and by_aux:
        print(f'\nСлужебные вызовы петли (--deep) по вкладу в полный прогон:')
        for k, v in sorted(by_aux.items(), key=lambda kv: kv[1], reverse=True)[:8]:
            print(f'  {v / 60.0:>8.1f} мин  {k}')

    print('\nКак читать: «calc %» — доля расчёта признаков в вызове бэктеста.'
          '\n«петля мкс/бар» — цена бара без расчёта и служебных вызовов. Если у'
          '\nсемейств со структурно одинаковым циклом она различается в разы —'
          '\nсмотреть --deep: там видно, сколько съедают служебные вызовы и сколько'
          '\nсделок на бэктест. «свёртка» — во сколько раз сократится вызов, если'
          '\ncalc считать 1 раз на все пары SL/TP.'
          '\nПорядок работ: calc % > 30 → свёртка SL/TP + векторизация calc;'
          '\nпетля мкс/бар > 60 у дешёвых семейств → numpy-индексация петли.')
    return 0


# ── Конец файла ──
# (служебных функций больше нет)


if __name__ == '__main__':
    sys.exit(main())
