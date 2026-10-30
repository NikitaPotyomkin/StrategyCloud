"""«По пылинкам»: лестница частичных закрытий по потенциалу дня — ОЦЕНКА.

Запуск:  python.exe sim_peak_ladder.py            # таблица + journals/peak_ladder.csv
         python.exe sim_peak_ladder.py --days     # разбивка по дням для первой лестницы

Идея (согласована 30.10):
  вместо одного «закрыть всё» режем книгу ПОРЦИЯМИ по мере роста потенциала:
  перевалили 50% эталона — закрыли часть, 75% — ещё часть, 100% — остаток.
  Так видно, куда история докатилась ПОСЛЕ каждого среза, а не только итог.

Чем отличается от sim_exit_rules.py:
  там правила «закрыть ВСЁ» (A/B/C) и итог = потенциал в момент выхода;
  здесь книга режется по долям, часть остаётся открытой и продолжает жить.

Данные: trades_db.equity_samples, замер раз в ~5 мин.
  potential(t) = equity(t) - balance_начала_суток - внешние деньги к t
               = реализованное с начала дня + floating(t)
  floating(t)  = equity(t) - balance(t)   (та самая «висящая» часть)

Как считается срез (модель, а не бухгалтерия):
  в момент t закрываем долю f ОТ ТЕКУЩЕЙ КНИГИ; фиксируется f*book*floating(t).
  Позиции масштабируются пропорционально, поэтому остаток несёт
  (1 - f)*book*floating дальше. Потенциал счёта при этом непрерывен:
  закрытое уходит в balance, висящее уменьшается на ту же сумму.

Допущения (важно):
  * доля книги ≈ доля объёма: частичное закрытие «по пылинкам» в реальности
    режется по каждому тикету, и там уже мешают volume_step / volume_min;
  * выход по цене замера (~5 мин), внутрибарного пути нет;
  * комиссии/свопы не вычтены (потенциал = profit+swap);
  * остаток, если он остался, оценивается по floating на последнем замере суток;
  * день считается законченным после последнего среза — новых входов нет.

Ограничение по данным: траектория ОТДЕЛЬНОЙ позиции в базе не хранится —
  position_peak пишет только пик и дно за день. Поэтому лестница по одной
  сделке на истории не воспроизводится, а по счёту — да (equity_samples полный).
  Частоту срабатывания правила по отдельным сделкам смотрит peak_trim.py --eval.
"""

import sys

import numpy as np
import pandas as pd

import trades_db
from sim_exit_rules import MIN_SAMPLES, SRV_OFFSET_H, _flows

CSV_PATH = 'journals/peak_ladder.csv'

# Лестницы: (доля эталона, какую долю ТЕКУЩЕЙ книги закрыть в этот момент).
LADDERS = (
    ('всё сразу на 50% эталона', ((0.50, 1.00),)),
    ('2 ступени 50/75, по 1/2', ((0.50, 0.50), (0.75, 0.50))),
    ('3 ступени 50/75/100, по 1/3', ((0.50, 1 / 3), (0.75, 1 / 3), (1.00, 1 / 3))),
    ('4 ступени 25/50/75/100, по 1/4', ((0.25, 0.25), (0.50, 0.25),
                                        (0.75, 0.25), (1.00, 0.25))),
    ('3 ступени по 30% от книги', ((0.50, 0.30), (0.75, 0.30), (1.00, 0.30))),
)


def _load():
    """{день: {'p': потенциал по замерам, 'fl': floating по тем же замерам}}."""
    con = trades_db.connect()
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(equity_samples)")}
        _flt = ", floating_total" if 'floating_total' in cols else ""
        df = pd.read_sql(
            "SELECT ts, balance, equity{} FROM equity_samples".format(_flt), con)
    finally:
        con.close()
    if df.empty:
        return {}

    df['ts'] = pd.to_numeric(df['ts'], errors='coerce')
    df['balance'] = pd.to_numeric(df['balance'], errors='coerce')
    df['equity_'] = pd.to_numeric(df['equity'], errors='coerce')
    df = df[df['equity_'].notna() & df['balance'].notna()]
    df = df.sort_values('ts').reset_index(drop=True)
    df['dt'] = (pd.to_datetime(df['ts'], unit='s', utc=True)
                + pd.Timedelta(hours=SRV_OFFSET_H))
    df['day'] = df['dt'].dt.date
    df['weekend'] = df['dt'].dt.weekday >= 5
    df['bal_start'] = df['day'].map(df.groupby('day')['balance'].first())

    fr = _flows()
    df['ext'] = 0.0
    if not fr.empty:
        _ext = np.zeros(len(df), dtype=float)
        _days = df['day'].to_numpy()
        _ts = df['ts'].to_numpy(dtype=float)
        for _day in pd.unique(_days):
            _f_day = fr[fr['day'] == _day]
            if _f_day.empty:
                continue
            _ft = _f_day['ts_true'].to_numpy(dtype=float)
            _cum = np.cumsum(_f_day['amount'].to_numpy(dtype=float))
            _mask = _days == _day
            _idx = np.searchsorted(_ft, _ts[_mask], side='right') - 1
            _ext[_mask] = np.where(_idx >= 0,
                                   _cum[np.clip(_idx, 0, len(_cum) - 1)], 0.0)
        df['ext'] = _ext

    df['potential'] = df['equity_'] - df['bal_start'] - df['ext']
    df['floating'] = df['equity_'] - df['balance']

    out = {}
    for day, x in df.groupby('day', sort=True):
        if bool(x['weekend'].iloc[0]) or len(x) < MIN_SAMPLES:
            continue
        out[day] = {
            'p': x['potential'].to_numpy(dtype=float),
            'fl': x['floating'].to_numpy(dtype=float),
        }
    return out


def ladder(p, fl, ref, steps):
    """Лестница срезов по потенциалу дня.

    Возвращает зафиксированное, стоимость остатка на конец суток и итог,
    плюс максимум потенциала ПОСЛЕ последнего среза — «куда докатилось».
    """
    book = 1.0            # какая доля книги ещё открыта
    locked = 0.0          # ₽, зафиксированные срезами
    idx_last = -1         # индекс последнего среза
    fired = []            # [(уровень, индекс, потенциал, закрытая доля книги)]

    for level, frac in steps:
        thr = level * ref
        sub = p[idx_last + 1:]
        hit = np.nonzero(sub >= thr)[0]
        if not len(hit):
            break                     # уровни растут — выше уже не сработает
        i = idx_last + 1 + int(hit[0])
        part = frac * book
        locked += part * float(fl[i])
        book -= part
        fired.append((level, i, float(p[i]), part))
        idx_last = i

    tail = p[idx_last + 1:] if idx_last + 1 < len(p) else np.array([])
    after_max = float(np.max(tail)) if len(tail) else np.nan
    rem = book * float(fl[-1])
    return {
        'total': locked + rem,
        'locked': locked,
        'rem': rem,
        'book_left': book,
        'fired': len(fired),
        'steps': fired,
        'after_max': after_max,
        'last_i': idx_last,
    }


def _rows(days, ref, steps):
    rows = []
    for day, d in days.items():
        r = ladder(d['p'], d['fl'], ref, steps)
        r['day'] = day
        r['peak'] = float(np.max(d['p']))
        r['base'] = float(d['p'][-1])
        r['delta'] = r['total'] - r['base']
        rows.append(r)
    return rows


def _agg(rows):
    total = np.array([r['total'] for r in rows], dtype=float)
    locked = np.array([r['locked'] for r in rows], dtype=float)
    rem = np.array([r['rem'] for r in rows], dtype=float)
    delta = np.array([r['delta'] for r in rows], dtype=float)
    return {
        'сумма': float(total.sum()),
        'среднее': float(total.mean()),
        'дней': len(rows),
        'сработало': int(sum(1 for r in rows if r['fired'])),
        'срезов': int(sum(r['fired'] for r in rows)),
        'зафиксировано': float(locked.sum()),
        'остаток': float(rem.sum()),
        'плюсовых': int((total > 0).sum()),
        'худший': float(total.min()),
        'лучший': float(total.max()),
        'дельта_к_базе': float(delta.sum()),
    }


def main():
    show_days = '--days' in sys.argv

    days = _load()
    if not days:
        print("нет данных: equity_samples пуст или суток с {} и более замерами нет"
              .format(MIN_SAMPLES))
        return 0

    first, last = min(days), max(days)
    peaks = np.array([float(np.max(d['p'])) for d in days.values()])
    base = float(np.array([float(d['p'][-1]) for d in days.values()]).sum())
    med = float(np.median(peaks))

    print("торговых дней: {}   период: {} — {}".format(
        len(days), first.strftime('%d.%m'), last.strftime('%d.%m')))
    print("эталон = медиана пиков дня: {:,.0f} ₽".format(med))
    print("база «ничего не делаем» (потенциал на конец суток): {:+,.0f} ₽"
          .format(base))
    print("потолок «закрыть всё ровно на пике» (недостижим): {:+,.0f} ₽"
          .format(float(peaks.sum())))

    rows = []
    for name, steps in LADDERS:
        rs = _rows(days, med, steps)
        a = _agg(rs)
        a['лестница'] = name
        a['эталон, ₽'] = med
        a['доля остатка'] = round(float(np.mean([r['book_left'] for r in rs])), 4)
        rows.append(a)

    out = pd.DataFrame(rows)[['лестница', 'эталон, ₽', 'сумма', 'среднее', 'дней',
                              'сработало', 'срезов', 'зафиксировано', 'остаток',
                              'доля остатка', 'плюсовых', 'худший', 'лучший',
                              'дельта_к_базе']]
    out = out.sort_values('сумма', ascending=False).reset_index(drop=True)

    print("\n=== лестницы частичных закрытий, отсортировано по сумме ===")
    print(out.to_string(
        index=False,
        formatters={'сумма': lambda v: '{:+,.0f}'.format(v),
                    'среднее': lambda v: '{:+,.0f}'.format(v),
                    'зафиксировано': lambda v: '{:,.0f}'.format(v),
                    'остаток': lambda v: '{:+,.0f}'.format(v),
                    'худший': lambda v: '{:+,.0f}'.format(v),
                    'лучший': lambda v: '{:+,.0f}'.format(v),
                    'дельта_к_базе': lambda v: '{:+,.0f}'.format(v)}))

    # Разбивка по дням для первой лестницы (или --days для конкретной)
    name, steps = LADDERS[1]
    if '--ladder' in sys.argv:
        i = sys.argv.index('--ladder')
        if len(sys.argv) > i + 1:
            _want = sys.argv[i + 1]
            for _n, _s in LADDERS:
                if _want.lower() in _n.lower():
                    name, steps = _n, _s
                    break

    rs = _rows(days, med, steps)
    print("\n=== по дням: {} (эталон {:,.0f} ₽) ===".format(name, med))
    print("  день     пик, ₽  порог50, ₽  срезов  зафикс., ₽  остаток, ₽  итог, ₽  "
          "дельта, ₽  после среза")
    for r in rs:
        thr50 = 0.5 * med
        print("  {:>5}  {:>9,.0f}  {:>10,.0f}  {:>6}  {:>10,.0f}  {:>10,.0f}  "
              "{:>9,.0f}  {:>9,.0f}  {:>11}".format(
                  r['day'].strftime('%d.%m'), r['peak'], thr50, r['fired'],
                  r['locked'], r['rem'], r['total'], r['delta'],
                  ('{:,.0f}'.format(r['after_max'])
                   if r['after_max'] == r['after_max'] else '—')))

    _a = _agg(rs)
    print("\nитог лестницы: {:+,.0f} ₽ ({:+,.0f} ₽/день, срезов {}, сработало в {} "
          "из {} дней); зафиксировано {:,.0f} ₽, остаток {:+,.0f} ₽".format(
              _a['сумма'], _a['среднее'], _a['срезов'], _a['сработало'],
              _a['дней'], _a['зафиксировано'], _a['остаток']))
    print("для сравнения — факт (держим до конца): {:+,.0f} ₽  →  лестница {:+,.0f} ₽"
          .format(base, _a['сумма'] - base))

    try:
        csv = out.copy()
        for c in ('сумма', 'среднее', 'зафиксировано', 'остаток', 'худший',
                  'лучший', 'дельта_к_базе'):
            csv[c] = pd.to_numeric(csv[c], errors='coerce').round(2)
        csv.to_csv(CSV_PATH, index=False, encoding='utf-8-sig', decimal=',')
        print("\nCSV: {}".format(CSV_PATH))
    except Exception as exc:
        print("\nCSV не записан: {!r}".format(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
