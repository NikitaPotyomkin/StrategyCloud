"""Мониторинг решений пик-трима: только чтение + запись CSV.

Зачем нужен: решение принимается по формуле, которой не видно в дэше.
Каждый снимок пишет в journals/peak_trim_watch.csv:

    potential = реализованный P&L сделок дня + плавающая (equity - balance)
    per_lot   = potential / ПЛАН дня (сигма лотов из journals/active_state.json)
    ratio     = per_lot / эталон (медиана дневных пиков Р/лот по дням до сегодня)
    armed     = ratio >= trail_act (2.0 эталона) — с этого момента копится пик
    hit       = ratio <= пик x (1 - trail_pct) — в этот момент бот режет счёт

Формулы берутся из самого peak_trim (импорт модуля), чтобы не было второй
правды. Скрипт ничего не открывает и не закрывает, таблицы бота не пишет,
к peak_trim.peak_trim не обращается. Пик дня ведёт сам — в
journals/peak_trim_watch_state.json (у бота он в памяти и теряется при
рестарте, здесь сохраняется — расхождение тоже видно).

Запуск:
    python peak_trim_watch.py                # один снимок
    python peak_trim_watch.py --every 300    # снимок каждые 5 минут
    python peak_trim_watch.py --summary      # сводка по дням из CSV
    python peak_trim_watch.py --summary --days 7
"""

import argparse
import csv
import datetime
import json
import os
import time

from config import PeakTrimParams
import peak_trim as pt
import trades_db

_HERE = os.path.dirname(os.path.abspath(__file__))
WATCH_CSV = os.path.join(_HERE, 'journals', 'peak_trim_watch.csv')
WATCH_STATE = os.path.join(_HERE, 'journals', 'peak_trim_watch_state.json')

FIELDS = [
    'ts', 'day', 'potential', 'realized_day', 'floating', 'book_vol', 'plan_vol',
    'per_lot', 'ref', 'ratio', 'peak', 'armed', 'hit', 'cuts', 'dirty',
    'act_rub', 'cut_rub', 'book_vs_plan_pct', 'note',
    'book_vs_plan_pct', 'note',
]


def _num(value, nd=0):
    """Число с пробелами между разрядами — как в остальных логах проекта."""
    try:
        return f"{float(value):,.{nd}f}".replace(',', ' ')
    except (TypeError, ValueError):
        return '—'


def _state_read(day):
    try:
        with open(WATCH_STATE, 'r', encoding='utf-8') as fh:
            st = json.load(fh)
        if not isinstance(st, dict):
            st = {}
    except Exception:
        st = {}
    if str(st.get('day') or '') != str(day):
        st = {'day': day, 'peak': 0.0, 'armed_ts': None,
              'episodes': 0, 'last_hit': False}
    return st


def _state_write(state):
    try:
        tmp = WATCH_STATE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, WATCH_STATE)
    except Exception as exc:
        print(f"  [WATCH] состояние не сохранено: {exc!r}", flush=True)


def _csv_write(row):
    try:
        os.makedirs(os.path.dirname(WATCH_CSV), exist_ok=True)
        header = not (os.path.exists(WATCH_CSV) and os.path.getsize(WATCH_CSV) > 0)
        with open(WATCH_CSV, 'a', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction='ignore')
            if header:
                w.writeheader()
            w.writerow(row)
    except Exception as exc:
        print(f"  [WATCH] строка не записана: {exc!r}", flush=True)


def snapshot(cfg=None, save=True):
    """Один снимок решения. Возвращает строку-словарь или None."""
    cfg = cfg or PeakTrimParams()
    try:
        import MetaTrader5 as mt5
    except Exception as exc:
        print(f"  [WATCH] нет MetaTrader5: {exc!r}", flush=True)
        return None
    if not trades_db._ensure_mt5(verbose=False):
        print("  [WATCH] нет соединения с MT5 — снимок пропущен", flush=True)
        return None
    acc = mt5.account_info()
    if acc is None:
        print("  [WATCH] account_info пуст — снимок пропущен", flush=True)
        return None
    positions = mt5.positions_get() or []
    now = datetime.datetime.now()
    ts = int(now.timestamp())
    today = now.strftime('%Y-%m-%d')
    login = int(acc.login)
    tol = float(getattr(cfg, 'volume_tolerance_pct', 0.20))

    con = trades_db.connect()
    try:
        ref = pt._daily_ref(con, today, cfg, login)
        cur = pt._today_per_lot(con, acc, positions, today, login, tol)
        # Реальные срезы дня — из таблицы бота (watch считает только решение,
        # а факт исполнения виден лишь в peak_trim: mode='real' + retcode).
        cuts = 0
        try:
            _rc = con.execute(
                "SELECT COUNT(*) AS n FROM peak_trim WHERE day = ? AND mode = 'real'",
                (today,)).fetchone()
            cuts = int(_rc['n'] or 0) if _rc is not None else 0
        except Exception:
            cuts = 0
    finally:
        con.close()

    ref_val = float(ref.get('ref') or 0.0) if ref else 0.0
    per_lot = cur.get('per_lot')
    plan_vol = float(cur.get('plan_vol') or 0.0)
    book_vol = float(cur.get('vol') or 0.0)
    potential = float(cur.get('potential') or 0.0)
    realized = float(cur.get('realized') or 0.0)
    floating = float(cur.get('floating') or 0.0)

    ratio = None
    if per_lot is not None and ref_val > 0:
        ratio = float(per_lot) / ref_val

    act = float(getattr(cfg, 'trail_act', 2.0))
    trail = float(getattr(cfg, 'trail_pct', 0.25))
    min_ref = float(getattr(cfg, 'min_ref_per_lot', 500.0))

    state = _state_read(today)
    if ratio is not None and ratio >= act:
        if float(state.get('peak') or 0.0) < ratio:
            state['peak'] = round(float(ratio), 4)
        if state.get('armed_ts') is None:
            state['armed_ts'] = ts
    peak = float(state.get('peak') or 0.0)
    armed = peak > 0.0
    hit = bool(armed and ratio is not None and ratio >= act
               and ratio <= peak * (1.0 - trail))
    if hit and not bool(state.get('last_hit')):
        state['episodes'] = int(state.get('episodes') or 0) + 1
    state['last_hit'] = bool(hit)
    state['ts'] = ts
    state['ratio'] = round(float(ratio), 4) if ratio is not None else None

    act_rub = act * ref_val * plan_vol if (ref_val > 0 and plan_vol > 0) else 0.0
    cut_rub = (peak * (1.0 - trail) * ref_val * plan_vol
               if (armed and ref_val > 0 and plan_vol > 0) else 0.0)

    note = ''
    if ref_val <= 0:
        note = 'нет эталона'
    elif ref_val < min_ref:
        note = f'эталон < {_num(min_ref)} Р/лот — бот не оценивает'
    elif plan_vol <= 0:
        note = 'нет плана дня'
    elif book_vol > plan_vol * (1.0 + tol):
        note = 'книга больше плана'
    elif book_vol < plan_vol * (1.0 - tol) and plan_vol > 0:
        note = 'книга меньше плана'

    if cuts > 0:
        note = (note + '; ' if note else '') + f'срез {cuts}'

    row = {
        'ts': ts,
        'day': today,
        'potential': round(potential, 2),
        'realized_day': round(realized, 2),
        'floating': round(floating, 2),
        'book_vol': round(book_vol, 4),
        'plan_vol': round(plan_vol, 4),
        'per_lot': round(float(per_lot), 2) if per_lot is not None else '',
        'ref': round(ref_val, 2),
        'ratio': round(ratio, 4) if ratio is not None else '',
        'peak': round(peak, 4),
        'armed': int(armed),
        'cuts': int(cuts),
        'dirty': int(cuts > 0),
        'hit': int(hit),
        'act_rub': round(act_rub, 0),
        'cut_rub': round(cut_rub, 0),
        'book_vs_plan_pct': (round((book_vol - plan_vol) / plan_vol * 100.0, 1)
                             if plan_vol > 0 else ''),
        'note': note,
    }

    if save:
        _csv_write(row)
        _state_write(state)

    ratio_txt = f"{ratio * 100:.0f}%" if ratio is not None else '—'
    print(f"  [WATCH] {today} потенциал {_num(potential)} Р "
          f"(реал {_num(realized)} + плав {_num(floating)}) | "
          f"книга {book_vol:.2f}/{plan_vol:.2f} лот | "
          f"{_num(per_lot)} Р/лот | эталон {_num(ref_val)} | "
          f"отношение {ratio_txt} | пик {peak * 100:.0f}% | "
          f"актив {'да' if armed else 'нет'} | срез "
          f"{'ДА' if hit else 'нет'}"
          + (f" | {note}" if note else ''), flush=True)
    return row


def summary(days=None):
    """Сводка по дням из накопленного CSV (по дням, не по снимкам)."""
    if not os.path.exists(WATCH_CSV):
        print(f"  [WATCH] нет файла {WATCH_CSV} — сначала снимите хотя бы один снимок")
        return []
    rows = []
    with open(WATCH_CSV, 'r', encoding='utf-8') as fh:
        for r in csv.DictReader(fh):
            rows.append(r)
    if not rows:
        print("  [WATCH] CSV пустой")
        return []

    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    per_day = {}
    for r in rows:
        per_day.setdefault(r.get('day') or '', []).append(r)

    day_keys = sorted(per_day)
    if days:
        day_keys = day_keys[-int(days):]

    print(f"{'день':<12}{'сним':>5}{'пикР':>10}{'итогР':>10}{'отдалР':>10}"
          f"{'maxотн':>9}{'актив':>7}{'грязн':>7}{'план':>7}{'книга':>7}")
    total_give = 0.0
    dirty_give = 0.0
    dirty_days = 0
    for day in day_keys:
        chunk = per_day[day]
        pots = [x for x in (_f(r.get('potential')) for r in chunk) if x is not None]
        ratios = [x for x in (_f(r.get('ratio')) for r in chunk) if x is not None]
        if not pots:
            continue
        pot_max = max(pots)
        pot_last = pots[-1]
        give = pot_last - pot_max
        # итоги ниже: чистые и грязные дни считаются раздельно
        armed = any(str(r.get('armed')) == '1' for r in chunk)
        hit = any(str(r.get('hit')) == '1' for r in chunk)
        dirty = any(str(r.get('dirty')) == '1' for r in chunk)
        give_txt = f"({_num(give)})" if dirty else _num(give)
        if dirty:
            dirty_give += give
            dirty_days += 1
        else:
            total_give += give
        plan = _f(chunk[-1].get('plan_vol')) or 0.0
        book = _f(chunk[-1].get('book_vol')) or 0.0
        print(f"{day:<12}{len(chunk):>5}{_num(pot_max):>10}{_num(pot_last):>10}"
              f"{give_txt:>10}{(max(ratios) * 100 if ratios else 0):>8.0f}%"
              f"{('да' if armed else '—'):>7}{('ГРЯЗН' if dirty else ('срез?' if hit else '—')):>7}"
              f"{plan:>7.2f}{book:>7.2f}")
    print(f"\n  чисто: отдано от пиков {_num(total_give)} Р "
          f"({len(day_keys) - dirty_days} дн. без среза)")
    if dirty_days:
        print(f"  грязно: {_num(dirty_give)} Р за {dirty_days} дн. — "
              f"в скобках, для вывода не годится")
    print("  'отдалР' = потенциал в последнем снимке минус пик дня "
          "(минус — день выше пика; в скобках — день со срезом)")
    return rows


def main():
    ap = argparse.ArgumentParser(
        description='Мониторинг решений пик-трима: только чтение + CSV')
    ap.add_argument('--every', type=int, default=0,
                    help='снимать каждые N секунд (0 = один снимок)')
    ap.add_argument('--summary', action='store_true',
                    help='сводка по дням из journals/peak_trim_watch.csv')
    ap.add_argument('--days', type=int, default=None,
                    help='сколько последних дней показать в сводке')
    ap.add_argument('--act', type=float, default=None,
                    help='активация трейла, во сколько эталонов (по умолчанию из config)')
    ap.add_argument('--trail', type=float, default=None,
                    help='срез при откате от пика дня (по умолчанию из config)')
    args = ap.parse_args()

    if args.summary:
        summary(days=args.days)
        return 0

    base = PeakTrimParams()
    cfg = PeakTrimParams(
        enabled=bool(base.enabled),
        shadow=bool(base.shadow),
        pct=base.pct,
        trail_act=args.act if args.act is not None else base.trail_act,
        trail_pct=args.trail if args.trail is not None else base.trail_pct,
        keep_volume=base.keep_volume,
        min_ref_volume=base.min_ref_volume,
        lookback_days=base.lookback_days,
        ref_quantile=base.ref_quantile,
        volume_tolerance_pct=base.volume_tolerance_pct,
        min_ref_per_lot=base.min_ref_per_lot,
        min_money=base.min_money,
        log_from_pct=base.log_from_pct,
        single_shot=base.single_shot,
    )

    if args.every and args.every > 0:
        print(f"  [WATCH] цикл: снимок каждые {args.every} с, CSV: {WATCH_CSV}",
              flush=True)
        while True:
            try:
                snapshot(cfg=cfg)
            except Exception as exc:
                print(f"  [WATCH] снимок упал: {exc!r}", flush=True)
            time.sleep(max(10, int(args.every)))
    snapshot(cfg=cfg)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
