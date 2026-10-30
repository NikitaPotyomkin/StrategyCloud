"""Подбор правила «когда закрывать всё» по потенциалу дня.

Запуск:  python.exe sim_exit_rules.py            # таблица + journals/exit_rules.csv
         python.exe sim_exit_rules.py --top 20   # больше строк в таблице

Данные: trades_db.equity_samples, замер раз в ~5 мин.
Потенциал дня(t) = equity(t) - balance_начала_суток - внешние деньги к t
                 = реализованное с начала дня + floating.

Считаются три класса правил (плюс базовый «ничего не делаем»):

  A. ДОЛЯ ПИКА (hindsight, верхняя оценка): «закрываем всё, когда потенциал
     достиг s% от ЛУЧШЕГО значения дня». В реальном времени пик дня неизвестен,
     поэтому эти цифры — потолок, а не план.

  B. ТРЕЙЛИНГ ОТ МАКСИМУМА (executable): «если потенциал упал на d% от лучшего
     значения СЕГОДНЯ, закрываем всё». Это исполняется в реальном времени:
     нужен только текущий running max и порог.

  C. ФИКСИРОВАННАЯ ЦЕЛЬ: «закрываем всё при достижении T ₽ потенциала».

Допущения (важно):
  * день считается законченным после выхода — новых входов в этот день нет,
    иначе результаты правил несравнимы;
  * выход по цене замера (раз в ~5 мин), внутрибарного пути нет — реальный
    выход будет хуже на проскальзывание и комиссию;
  * комиссии/свопы в потенциале не вычтены (потенциал = profit+swap позиций);
  * итог правила за день = потенциал в момент срабатывания, иначе — потенциал
    на последнем замере суток.
"""

import sys

import numpy as np
import pandas as pd

import trades_db

SRV_OFFSET_H = 3
CSV_PATH = 'journals/exit_rules.csv'
NO_FLOW_SOURCES = ('cutoff', 'bootstrap')
MIN_SAMPLES = 20          # сутки с меньшим числом замеров не берём: шум


def _f(v, nd=0):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return '—'
    if x != x:
        return '—'
    return format(x, ',.{}f'.format(nd))


def _flows():
    """Внешние деньги по замерам: ts_true -> накопительно, и день операции."""
    try:
        import cashflow as _cf
        rows = _cf.ops_list(limit=5000)
    except Exception as exc:
        print("  cashflow недоступен ({}): вычет внешних денег отключён".format(exc))
        return pd.DataFrame(columns=['ts_true', 'day', 'amount'])
    recs = []
    for row in rows:
        try:
            _ts, amount, _kind, src = int(row[0]), float(row[1]), row[2], str(row[3] or '')
        except (TypeError, ValueError, IndexError):
            continue
        if src in NO_FLOW_SOURCES or amount == 0:
            continue
        # 'deals' — серверное время «под видом UTC» (сдвиг +3 ч), 'reconcile' — epoch
        shift = 0 if src in ('reconcile', 'manual') else SRV_OFFSET_H * 3600
        recs.append((_ts - shift, amount))
    if not recs:
        return pd.DataFrame(columns=['ts_true', 'day', 'amount'])
    fr = pd.DataFrame(recs, columns=['ts_true', 'amount'])
    fr['day'] = pd.to_datetime(fr['ts_true'] + SRV_OFFSET_H * 3600,
                               unit='s', utc=True).dt.date
    return fr.sort_values('ts_true').reset_index(drop=True)


def load_days():
    """{день: np.array(потенциал по замерам, по времени)}."""
    con = trades_db.connect()
    try:
        df = pd.read_sql(
            "SELECT ts, balance, equity FROM equity_samples", con)
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

    out = {}
    for day, x in df.groupby('day', sort=True):
        if bool(x['weekend'].iloc[0]) or len(x) < MIN_SAMPLES:
            continue
        out[day] = x['potential'].to_numpy(dtype=float)
    return out


def exit_share(p, share):
    """A: выйти при достижении share × пика дня."""
    peak = float(np.max(p))
    if peak <= 0:
        return float(p[-1]), False
    thr = share * peak
    hit = p >= thr
    if bool(hit.any()):
        i = int(np.argmax(hit))
        return float(p[i]), True
    return float(p[-1]), False


def exit_trail(p, drop):
    """B: выйти, когда потенциал упал на drop от running max этого дня."""
    best = -np.inf
    for v in p:
        if v > best:
            best = float(v)
        if best > 0 and v <= best * (1.0 - drop):
            return float(v), True
    return float(p[-1]), False


def exit_target(p, target):
    """C: выйти при потенциале >= target ₽."""
    hit = p >= target
    if bool(hit.any()):
        i = int(np.argmax(hit))
        return float(p[i]), True
    return float(p[-1]), False


def _evaluate(days, fn, param):
    rows = []
    for day, p in days.items():
        val, fired = fn(p, param)
        rows.append((day, val, fired))
    vals = np.array([r[1] for r in rows], dtype=float)
    fired = sum(1 for r in rows if r[2])
    return {
        'сумма': float(vals.sum()),
        'среднее': float(vals.mean()),
        'дней': len(rows),
        'сработало': fired,
        'плюсовых': int((vals > 0).sum()),
        'худший': float(vals.min()),
        'лучший': float(vals.max()),
    }


def main():
    top = 25
    if '--top' in sys.argv:
        i = sys.argv.index('--top')
        if len(sys.argv) > i + 1:
            top = int(sys.argv[i + 1])

    days = load_days()
    if not days:
        print("нет данных: equity_samples пуст или суток с {} и более замерами нет"
              .format(MIN_SAMPLES))
        return 0

    first, last = min(days), max(days)
    base = _evaluate(days, lambda p, _x: (float(p[-1]), False), None)
    peaks = np.array([float(np.max(p)) for p in days.values()])
    print("торговых дней: {}   период: {} — {}".format(
        len(days), first.strftime('%d.%m'), last.strftime('%d.%m')))
    print("замеров на день: {:.0f} в среднем".format(
        float(np.mean([len(p) for p in days.values()]))))
    print("база «ничего не делаем» (потенциал на конец суток): "
          "{:+,.0f} ₽   среднее {:+,.0f} ₽/день".format(base['сумма'], base['среднее']))
    print("потолок «закрыть всё ровно на пике» (недостижим): "
          "{:+,.0f} ₽   среднее {:+,.0f} ₽/день".format(
              float(peaks.sum()), float(peaks.mean())))

    rows = []

    def add(name, fn, param, note=''):
        res = _evaluate(days, fn, param)
        res['правило'] = name
        res['параметр'] = param
        res['примечание'] = note
        res['дельта_к_базе'] = res['сумма'] - base['сумма']
        rows.append(res)

    add('база: держим до конца дня', lambda p, _x: (float(p[-1]), False), None,
        'как есть сейчас')
    for share in (0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0):
        add('A: доля пика дня', exit_share, share, 'hindsight, потолок')
    for drop in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50):
        add('B: трейлинг от максимума', exit_trail, drop, 'executable')
    for target in (3000, 5000, 8000, 10000, 15000, 20000, 30000):
        add('C: цель в рублях', exit_target, float(target), 'executable')

    out = pd.DataFrame(rows)[['правило', 'параметр', 'сумма', 'среднее', 'дней',
                              'сработало', 'плюсовых', 'худший', 'лучший',
                              'дельта_к_базе', 'примечание']]
    out = out.sort_values('сумма', ascending=False).reset_index(drop=True)

    show = out.head(max(1, top)).copy()
    show['параметр'] = [('{:,.0f}%'.format(v * 100) if v is not None and v <= 1.0
                        else ('{:,.0f} ₽'.format(v) if v is not None else '—'))
                        for v in show['параметр']]
    print("\n=== правила выхода, отсортировано по сумме за период ===")
    print(show.to_string(index=False,
                         formatters={'сумма': lambda v: '{:+,.0f}'.format(v),
                                     'среднее': lambda v: '{:+,.0f}'.format(v),
                                     'худший': lambda v: '{:+,.0f}'.format(v),
                                     'лучший': lambda v: '{:+,.0f}'.format(v),
                                     'дельта_к_базе': lambda v: '{:+,.0f}'.format(v)}))

    best_exec = out[out['примечание'] == 'executable'].head(1)
    if not best_exec.empty:
        r = best_exec.iloc[0]
        print("\nлучшее ИСПОЛНИМОЕ правило: {} {} → {:+,.0f} ₽ "
              "({:+,.0f} ₽/день, сработало в {} из {} дней)".format(
                  r['правило'], r['параметр'], r['сумма'], r['среднее'],
                  int(r['сработало']), int(r['дней'])))

    try:
        csv = out.copy()
        for c in ('сумма', 'среднее', 'худший', 'лучший', 'дельта_к_базе'):
            csv[c] = pd.to_numeric(csv[c], errors='coerce').round(2)
        csv['параметр'] = [('' if v is None else str(v)) for v in csv['параметр']]
        csv.to_csv(CSV_PATH, index=False, encoding='utf-8-sig', decimal=',')
        print("\nCSV: {}".format(CSV_PATH))
    except Exception as exc:
        print("\nCSV не записан: {!r}".format(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
