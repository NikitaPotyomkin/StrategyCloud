"""Паритет ИНКРЕМЕНТА против полного прогона (Шаг 3, гейт для incremental_bars).

ЧТО ПРОВЕРЯЕТ
    Что «хвостовой» пересчёт (инкремент по новым барам) даёт ТОТ ЖЕ результат, что
    полный прогон по всему окну: profit, число сделок и журнал сделок по каждому
    комбо каждого семейства.

КАК (три прогона одного символа, окно как в проде)
    A. seed  — полный прогон по окну БЕЗ последних N бар: пишет v2-чекпойнт с
               журналами сделок («состояние кэша N бар назад»);
    B. опыт  — прогон по полному окну с incremental=True: движок видит ровно N
               новых бар и обязан считать «хвостом» по кэшу из A;
    C. эталон — полный прогон по полному окну (force_recalc).
    Сравниваются B и C (у них одинаковая история; A только сеет кэш).

ЗАЧЕМ
    Без зелёного паритета инкремент идёт вслепую: `_warmup.can_use_incremental`
    при ОТСУТСТВИИ записи в журнале паритета разрешает инкремент, а
    `_warmup.record_parity` до сих пор НИКЕМ не вызывался → журнал
    checkpoints/incremental_parity.json пуст, и любая ошибка warm-up прошла бы
    молча. Этот инструмент — тот, кто его заполняет.

ЧТО ПИШЕТ
    checkpoints/incremental_parity.json — по семейству:
        {'ok': bool, 'max_diff': float, 'checked_at': iso}
    После этого боевой `can_use_incremental` сам понижает проваленное семейство
    до полного прогона (без правки кода).

ЧТО НЕ ТРОГАЕТ
    Прод-флаг: config.incremental_bars НЕ меняется (используется копия конфига
    через dataclasses.replace). Ордера, позиции, trades.db — не трогаются.

ВНИМАНИЕ: инструмент запускается в ТОЙ ЖЕ папке, где лежат checkpoints/ и journals/,
и три прогона перезаписывают чекпойнт символа. Перед началом старый чекпойнт
сохраняется рядом как <symbol>.parity_backup.json; вернуть его — флагом --restore.

ЗАПУСК
    python tools/parity_check.py                      # символ из config, 3 новых бара
    python tools/parity_check.py --symbol EURUSDrfd --bars-new 6
    python tools/parity_check.py --families percentile,runs,doji --bars-new 3
    python tools/parity_check.py --restore            # вернуть чекпойнт до прогона

КОД ВОЗВРАТА
    0 — расхождений нет ни у одного проверенного семейства (инкремент разрешён);
    1 — есть расхождения (они уже записаны в журнал паритета и будут считаться
        полным прогоном) или проверить не удалось.
"""
import argparse
import dataclasses
import json
import os
import shutil
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)


def _ck_path(symbol):
    import functions
    return os.path.join(functions._checkpoint_dir(), f'{symbol}.json')


def _backup_ck(symbol):
    """Сохранить текущий чекпойнт рядом, чтобы можно было вернуть (--restore)."""
    src = _ck_path(symbol)
    if not os.path.exists(src):
        return None
    dst = os.path.join(os.path.dirname(src), f'{symbol}.parity_backup.json')
    shutil.copy2(src, dst)
    return dst


def _rows_with_journals(symbol):
    """Семейства, у которых в чекпойнте есть журналы сделок (v2)."""
    import functions
    rows = functions.load_checkpoint(symbol)
    if isinstance(rows, dict):                       # разные версии схемы чекпойнта
        rows = rows.get('results') or rows.get('rows') or []
    if not rows:
        return set()
    fams, seen = set(), set()
    incomplete = set()
    for r in rows:
        fam = r.get('type')
        seen.add(fam)
        t = r.get('trades')
        if isinstance(t, list) and t:
            fams.add(fam)
        else:
            incomplete.add(fam)
    return fams - incomplete


def _plan_preview(families, symbol, window_bars):
    """Что движок собирается инкрементировать: класс памяти + warm-up."""
    from strategies._warmup import memory_class, warmup_bars, can_use_incremental
    import functions
    ck = functions._checkpoint_dir()
    out = {}
    for fam in families:
        cls = memory_class(fam)
        wu = warmup_bars(fam, None, 0, window_bars)
        out[fam] = {
            'class': cls,
            'warmup': wu,
            'allowed': bool(can_use_incremental(ck, fam, None, 0, window_bars)),
        }
    return out


def _key(row):
    return (row.get('type'), str(row.get('param_key')), row.get('sl_points'),
            row.get('tp_points'))


def _index(results):
    return {_key(r): r for r in (results or [])}


def main():
    ap = argparse.ArgumentParser(description='Паритет инкремента против полного прогона')
    ap.add_argument('--symbol', default=None, help='символ (по умолчанию 1-й из config)')
    ap.add_argument('--bars-new', type=int, default=3, dest='bars_new',
                    help='сколько «новых» бар имитировать (по умолчанию 3)')
    ap.add_argument('--families', default=None, help='ограничить список семейств')
    ap.add_argument('--tol', type=float, default=None, help='допуск (по умолчанию PARITY_TOL)')
    ap.add_argument('--restore', action='store_true',
                    help='вернуть чекпойнт из <symbol>.parity_backup.json и выйти')
    ap.add_argument('--dry-plan', action='store_true',
                    help='только показать план инкремента по чекпойнту, без прогонов')
    args = ap.parse_args()

    from config import build_default_configs
    app = build_default_configs()
    sp = app.strategy_params
    bt = app.backtest_config
    window_bars = bt.backtest_days * 24
    symbol = args.symbol or (list(bt.symbols)[0] if bt.symbols else 'GBPUSDrfd')

    if args.restore:
        dst = _ck_path(symbol)
        bak = os.path.join(os.path.dirname(dst), f'{symbol}.parity_backup.json')
        if not os.path.exists(bak):
            print(f'Нет бэкапа {bak} — возвращать нечего.')
            return 1
        shutil.copy2(bak, dst)
        print(f'Чекпойнт {symbol} возвращён из бэкапа.')
        return 0

    from strategies._warmup import PARITY_TOL, record_parity, load_parity
    tol = PARITY_TOL if args.tol is None else float(args.tol)

    import MetaTrader5 as mt5
    import functions
    import data_loader
    from datetime import timedelta

    if not mt5.initialize():
        print(f'MT5 initialize не удался: {mt5.last_error()}')
        return 1
    mt5.symbol_select(symbol, True)
    info = mt5.symbol_info(symbol)
    if info is None:
        print(f'{symbol}: symbol_info вернул None')
        return 1
    h1 = data_loader.load_h1(symbol)
    if h1 is None or len(h1) < window_bars + args.bars_new + 5:
        print(f'{symbol}: баров {0 if h1 is None else len(h1)} — мало для окна {window_bars}')
        return 1

    print(f'Паритет ИНКРЕМЕНТА | символ {symbol} | окно {window_bars} бар | '
          f'новых бар: {args.bars_new} | допуск {tol:g}')
    print(f'Баров всего: {len(h1)} | последний: {h1.index[-1]}')

    if args.dry_plan:
        fams = _rows_with_journals(symbol)
        if not fams:
            print('В чекпойнте нет журналов сделок (v2) — инкремент невозможен ни для '
                  'одного семейства. Дождитесь полного прогона (сб) или прогоните '
                  'этот инструмент ещё раз после него.')
            return 1
        preview = _plan_preview(fams, symbol, window_bars)
        rec = load_parity(functions._checkpoint_dir())
        print(f'\n{"family":<18}{"класс":>7}{"warm-up":>9}{"инкремент":>10}{"паритет":>9}')
        for fam in sorted(fams):
            p = preview[fam]
            pr = rec.get(fam, {})
            state = 'не проверялся' if not pr else ('OK' if pr.get('ok') else 'ПРОВАЛ')
            print(f'{fam:<18}{p["class"]:>7}{str(p["warmup"]):>9}'
                  f'{("да" if p["allowed"] else "нет"):>10}{state:>9}')
        return 0

    def make_sd(df):
        return {symbol: {
            'df_h1': df,
            'current_hour': (df.index[-1] + timedelta(hours=1)).replace(
                minute=0, second=0, microsecond=0),
            'forming_bar': None,
            'info': info,
        }}

    def run(df, incremental, tag):
        import functions as _fn
        cfg = dataclasses.replace(bt, incremental_bars=bool(incremental))
        t0 = time.perf_counter()
        print(f'\n── {tag}: {"ИНКРЕМЕНТ" if incremental else "полный прогон"} '
              f'({len(df)} бар)…', flush=True)
        _top, results = _fn.run_full_backtest(
            [symbol], make_sd(df), sp, cfg,
            test_strategy=None, test_mode=False,
            force_recalc=not incremental, incremental=bool(incremental),
            is_night_run=True)
        dt = time.perf_counter() - t0
        print(f'   {tag}: {dt / 60.0:.1f} мин, комбинаций {len(results or [])}',
              flush=True)
        return dt, (results or [])

    bak = _backup_ck(symbol)
    print(f'Чекпойнт до прогонов: {bak if bak else "отсутствовал"}')

    n = max(1, args.bars_new)
    seed_df = h1.iloc[:-n]
    full_df = h1

    _, _seed = run(seed_df, False, 'A seed (кэш N бар назад)')
    fams_with_journals = _rows_with_journals(symbol)
    print(f'Семейств с v2-журналами после seed: {len(fams_with_journals)}')

    t_inc, inc = run(full_df, True, 'B опыт (инкремент)')
    t_ref, ref = run(full_df, False, 'C эталон (полный)')

    idx_i, idx_r = _index(inc), _index(ref)
    if args.families:
        want = {f.strip() for f in args.families.split(',') if f.strip()}
        keys = [k for k in idx_r if k[0] in want]
    else:
        keys = list(idx_r)

    preview = _plan_preview(sorted({k[0] for k in idx_r}), symbol, window_bars)
    ck_dir = functions._checkpoint_dir()

    per_fam = {}
    for k in keys:
        fam = k[0]
        d = per_fam.setdefault(fam, {'n': 0, 'diff': 0.0, 'bad': [], 'no_journal': 0,
                                     'skip': None})
        if preview.get(fam, {}).get('warmup') is None:
            d['skip'] = f'класс памяти {preview.get(fam, {}).get("class")} — инкремент запрещён'
            continue
        if fam not in fams_with_journals:
            d['no_journal'] += 1
            continue
        a, b = idx_i.get(k), idx_r.get(k)
        if a is None or b is None:
            d['bad'].append(f'{k}: комбо есть только в одном прогоне')
            continue
        d['n'] += 1
        try:
            import trade_log as _tl
            ok_j, diff_j = _tl.parity(a.get('trades'), b.get('trades'), tol)
        except Exception as exc:
            ok_j, diff_j = False, float('inf')
            d['bad'].append(f'{k}: журнал не сравнить ({exc!r})')
        dp = abs(float(a.get('profit') or 0.0) - float(b.get('profit') or 0.0))
        dn = int(a.get('n_trades') or 0) - int(b.get('n_trades') or 0)
        diffs = []
        if dp > tol:
            diffs.append(f'profit {dp:.6g}')
        if dn != 0:
            diffs.append(f'сделок {dn:+d}')
        if not ok_j:
            diffs.append(f'журнал {diff_j:.6g}')
        d['diff'] = max(d['diff'], 0.0 if diff_j == float('inf') else diff_j, dp)
        if diffs:
            d['bad'].append(f'{k}: ' + ', '.join(diffs))

    print()
    hdr = (f'{"family":<18}{"комбо":>7}{"класс":>7}{"warm-up":>9}'
           f'{"max_diff":>12}{"вердикт":>14}')
    print(hdr)
    print('-' * len(hdr))

    bad_fams = []
    for fam in sorted(per_fam):
        d = per_fam[fam]
        p = preview.get(fam, {})
        if d['n'] == 0:
            why = d['skip'] or (f'нет v2-журналов ({d["no_journal"]} комбо)' if d['no_journal']
                                else 'нет данных')
            print(f'{fam:<18}{0:>7}{str(p.get("class")):>7}{str(p.get("warmup")):>9}'
                  f'{"—":>12}{"не проверено":>14}   {why}')
            continue
        ok = not d['bad']
        if not ok:
            bad_fams.append(fam)
        print(f'{fam:<18}{d["n"]:>7}{str(p.get("class")):>7}{str(p.get("warmup")):>9}'
              f'{d["diff"]:>12.6g}{("OK" if ok else "ПРОВАЛ"):>14}')
        if not ok:
            for b in d['bad'][:3]:
                print(f'    ↳ {b}')
        record_parity(ck_dir, fam, d['diff'], tol)

    checked = sum(1 for f in per_fam if per_fam[f]['n'] > 0)
    print('-' * len(hdr))
    print(f'Проверено семейств: {checked} из {len(per_fam)} | '
          f'провалов: {len(bad_fams)}')
    print(f'Время: seed+инкремент {t_inc / 60.0:.1f} мин против полного {t_ref / 60.0:.1f} мин '
          f'({(t_ref / t_inc) if t_inc > 0 else 0:.2f}x)')
    if t_inc > 0.7 * t_ref and checked:
        print('  ! инкремент по времени почти как полный прогон — возможно, движок ушёл '
              'на полный путь (нет v2-журналов у части комбо или warm-up недоступен). '
              'Тогда «OK» означает лишь, что полный путь совпал сам с собой.')
    print(f'Журнал паритета: {os.path.join(ck_dir, "incremental_parity.json")}')

    if bad_fams:
        print('\nПРОВАЛЫ (эти семейства боевой can_use_incremental сам понизит до '
              'полного прогона):')
        for f in bad_fams:
            print(f'  {f}')
        print('Причина чаще всего: warm-up мал для семейства (см. strategies/_warmup.py — '
              'класс памяти/период) либо семейство мутирует кадр.')
        return 1

    if checked == 0:
        print('\nНи одно семейство не проверено: нет v2-журналов в чекпойнте. '
              'Сначала полный прогон (сб), потом этот инструмент.')
        return 1

    print('\nПаритет инкремента зелёный. Прод-флаг не менялся: включать '
          'incremental_bars=True самостоятельно (план 25.10).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
