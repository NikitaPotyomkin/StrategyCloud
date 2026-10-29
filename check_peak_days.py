"""Пик суммарной прибыли по открытым позициям за ТОРГОВЫЕ сутки.

Запуск:  python.exe check_peak_days.py            # печать + journals/peak_daily.csv
         python.exe check_peak_days.py --no-csv   # только печать

Что считает:
  fl_пик = max(floating_total) за сутки (серверное время, UTC+3).
  floating_total = equity - balance = суммарный плавающий P&L открытых позиций
  (profit + swap), то есть ровно «прибыль по позициям» на момент замера.
  Замер идёт раз в ~5 минут, поэтому пик — это МАКСИМУМ ИЗ ЗАМЕРОВ (нижняя
  оценка: между замерами значение могло уйти и выше, и глубже).

Выходные (сб/вс) в анализ не входят вообще: рынок закрыт, сэмплер пишет
одно и то же замороженное значение, и такие дни только портят картину.

Колонки сверки с финстейтментом:
  баланс нач  — balance первого замера суток;
  поп/выв     — внешние деньги за сутки из balance_ops (пополнения, выводы,
                balance/credit/charge-сделки). Входящий остаток периода учёта
                (source='cutoff') и 'bootstrap' не считаются: это не движение;
  реализовано — Δбаланса минус поп/выв, то есть результат по ЗАКРЫТЫМ сделкам.
                Именно эту цифру надо сравнивать с финстейтментом.
Пик и «реализовано» совпадать не обязаны: пик — суммарный floating всех
открытых позиций (убыточная минус прибыльная, с взаимозачётом), а финстейтмент
считает закрытые сделки. Убыточные позиции закрываются, прибыльные висят.
"""

import sys

import pandas as pd

import trades_db

SRV_OFFSET_H = 3     # как в risk_equity_block: серверное время = UTC+3
CSV_PATH = 'journals/peak_daily.csv'


def _f(v, nd=0, dash='—'):
    """Число в строку; None / NaN -> прочерк."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return dash
    if x != x:            # NaN
        return dash
    return format(x, ',.{}f'.format(nd))


def _max_run(vals):
    """Самая длинная серия одинаковых значений — признак замороженных данных."""
    best = run = 1
    prev = None
    for v in vals:
        if prev is not None and v == prev:
            run += 1
            best = max(best, run)
        else:
            run = 1
        prev = v
    return best if len(vals) else 0


def _external_flows():
    """Внешние деньги по суткам: {серверная дата: сумма ₽}.

    balance_ops.ts у сделок — это серверное время, записанное как UTC
    (та же особенность, что у deals.time), поэтому дата берётся как есть,
    без сдвига: она уже совпадает с сутками equity_samples (ts + 3 ч).
    """
    try:
        import cashflow as _cf
    except Exception as exc:
        print("  cashflow недоступен ({}): вычет пополнений/выводов отключён".format(exc))
        return {}
    try:
        rows = _cf.ops_list(limit=5000)
    except Exception as exc:
        print("  balance_ops не прочитан ({}): вычет отключён".format(exc))
        return {}

    out = {}
    for row in rows:
        try:
            _ts, amount, _kind, src = int(row[0]), float(row[1]), row[2], str(row[3] or '')
        except (TypeError, ValueError, IndexError):
            continue
        if src in ('cutoff', 'bootstrap'):
            continue                    # входящий остаток — не движение средств
        day = pd.to_datetime(_ts, unit='s', utc=True).date()
        out[day] = out.get(day, 0.0) + amount
    return out


def _dump(df, day=None):
    """Выгрузка ВСЕХ замеров в CSV (открывать в Excel или DB Browser).

    day: 'YYYY-MM-DD' (серверная дата) или None — весь период.
    """
    x = df if day is None else df[df['dt'].dt.strftime('%Y-%m-%d') == day]
    if x.empty:
        print("\nнечего выгружать: замеров за {} нет".format(day or 'весь период'))
        return
    cols = {'dt': 'время_сервер', 'ts': 'epoch', 'bal': 'balance',
            'equity': 'equity', 'fl': 'floating_₽', 'vol': 'объём_лот'}
    if 'n_positions' in x.columns:
        cols['n_positions'] = 'позиций'
    use = [c for c in cols if c in x.columns]
    out = x.sort_values('ts')[use].rename(columns=cols)
    for c in ('floating_₽', 'equity', 'balance', 'объём_лот'):
        if c in out.columns:
            out[c] = out[c].astype(float).round(2)
    path = ('journals/equity_samples_{}.csv'.format(day) if day
            else 'journals/equity_samples.csv')
    try:
        out.to_csv(path, index=False, encoding='utf-8-sig', decimal=',')
        print("\nвыгружено замеров: {} -> {}".format(len(out), path))
    except Exception as exc:
        print("\nCSV не записан: {!r}".format(exc))


def _tail(df, n=10):
    x = df[~df['weekend']].sort_values('ts').tail(n)
    print("\nпоследние {} замеров торговых суток (время серверное = UTC+{}):".format(
        len(x), SRV_OFFSET_H))
    print('{:<20}{:>14}{:>14}{:>12}{:>5}{:>8}'.format(
        'время', 'balance', 'equity', 'floating', 'поз', 'объём'))
    for _, r in x.iterrows():
        print('{:<20}{:>14}{:>14}{:>12}{:>5}{:>8}'.format(
            r['dt'].strftime('%d.%m %H:%M:%S'),
            _f(r.get('balance')),
            _f(r.get('equity')),
            _f(r.get('floating_total')),
            _f(r.get('n_positions')),
            _f(r.get('floating_volume'), 2)))


def main():
    con = trades_db.connect()
    try:
        df = pd.read_sql("SELECT * FROM equity_samples", con)
    finally:
        con.close()

    if df.empty:
        print("equity_samples пуст")
        return 0

    df['ts'] = pd.to_numeric(df['ts'], errors='coerce')
    df['fl'] = pd.to_numeric(df['floating_total'], errors='coerce')
    df['bal'] = (pd.to_numeric(df['balance'], errors='coerce')
                 if 'balance' in df.columns else pd.Series(float('nan'), index=df.index))
    df = df[df['fl'].notna()]
    df['dt'] = (pd.to_datetime(df['ts'], unit='s', utc=True)
                + pd.Timedelta(hours=SRV_OFFSET_H))
    df['day'] = df['dt'].dt.date
    df['weekend'] = df['dt'].dt.weekday >= 5          # сб/вс — вне анализа
    has_vol = 'floating_volume' in df.columns
    df['vol'] = (pd.to_numeric(df['floating_volume'], errors='coerce') if has_vol
                 else pd.Series(float('nan'), index=df.index))
    df = df.sort_values('ts')

    flows = _external_flows()

    first, last = df['dt'].min(), df['dt'].max()
    print("строк: {}   период: {} — {}   торговых дней: {}".format(
        len(df), first.strftime('%d.%m %H:%M'), last.strftime('%d.%m %H:%M'),
        df.loc[~df['weekend'], 'day'].nunique()))
    print("выходных в базе: {} суток / {} замеров — в расчёт не берутся".format(
        df.loc[df['weekend'], 'day'].nunique(), int(df['weekend'].sum())))
    print("внешние деньги (balance_ops): {} дней с движениями, сумма {:+,.0f} ₽".format(
        len(flows), float(sum(flows.values()))))
    print("ВАЖНО: сэмплер начал писать только {}. Дни раньше этой даты в графике "
          "пиков отсутствуют — по ним нет ни пиков, ни минимумов.".format(
              first.strftime('%d.%m.%Y %H:%M')))

    rows = []
    for day, x in df.groupby('day', sort=True):
        weekend = bool(x['weekend'].iloc[0])
        i = x['fl'].idxmax()
        vol_peak = x.loc[i, 'vol'] if has_vol else float('nan')
        m = x['vol'] > 0
        per_peak = float((x.loc[m, 'fl'] / x.loc[m, 'vol']).max()) if m.any() else float('nan')
        ext = float(flows.get(day, 0.0))
        rows.append({
            'день': day,
            'дн': 'сб' if weekend and x['dt'].iloc[0].weekday() == 5 else
                  ('вс' if weekend else ''),
            'замеров': len(x),
            'баланс нач': float(x['bal'].iloc[0]),
            'поп/выв': ext,
            'реализовано': float(x['bal'].iloc[-1] - x['bal'].iloc[0]) - ext,
            'пик ₽': float(x.loc[i, 'fl']),
            'время пика': x.loc[i, 'dt'].strftime('%H:%M'),
            'поз@пик': (float(x.loc[i, 'n_positions'])
                        if 'n_positions' in x.columns else float('nan')),
            'объём@пик': float(vol_peak) if pd.notna(vol_peak) else float('nan'),
            '₽/лот@пик': per_peak,
            'мин ₽': float(x['fl'].min()),
            'закрытие ₽': float(x['fl'].iloc[-1]),
            'одинак.подряд': _max_run(list(x['fl'])),
        })

    out = pd.DataFrame(rows)
    day_tbl = out[out['дн'] == ''].copy()          # только торговые дни

    if day_tbl.empty:
        print("торговых дней в базе нет")
        return 0

    show = day_tbl.drop(columns=['дн'])
    print("\n=== пик суммарной прибыли по позициям за торговые сутки ===")
    print(show.to_string(index=False,
                         formatters={'баланс нач': lambda v: '{:,.0f}'.format(v),
                                     'поп/выв': lambda v: '{:+,.0f}'.format(v),
                                     'реализовано': lambda v: '{:+,.0f}'.format(v),
                                     'пик ₽': lambda v: '{:,.0f}'.format(v),
                                     'мин ₽': lambda v: '{:,.0f}'.format(v),
                                     'закрытие ₽': lambda v: '{:,.0f}'.format(v),
                                     'объём@пик': lambda v: _f(v, 2),
                                     '₽/лот@пик': lambda v: _f(v, 0)}))

    _allneg = int((day_tbl['пик ₽'] < 0).sum())
    _neverneg = int((day_tbl['мин ₽'] >= 0).sum())
    print("\nторговых дней: {}".format(len(day_tbl)))
    print("дней с отрицательным пиком (ВСЕ замеры в минусе): {}".format(_allneg))
    print("дней, где ВСЕ замеры были в плюсе: {}".format(_neverneg))
    print("дней без объёма (₽/лот не посчитать): {}".format(
        int(day_tbl['₽/лот@пик'].isna().sum())))
    print("внешние деньги за эти дни: {:+,.0f} ₽".format(
        float(day_tbl['поп/выв'].sum())))
    print("реализовано за торговые дни (сверять с финстейтментом): {:+,.0f} ₽".format(
        float(day_tbl['реализовано'].sum())))
    print("отрицательных дней по реализованному результату: {}".format(
        int((day_tbl['реализовано'] < 0).sum())))

    top = day_tbl.nlargest(min(5, len(day_tbl)), 'пик ₽')
    print("\nТОП-5 пиков:")
    for _, r in top.iterrows():
        print("  {} {:>10,.0f} ₽ в {} · позиций {} · объём {} лот · "
              "закрытие {:,.0f} ₽ · реализовано {:+,.0f} ₽".format(
                  r['день'], r['пик ₽'], r['время пика'], _f(r['поз@пик']),
                  _f(r['объём@пик'], 2), r['закрытие ₽'], r['реализовано']))

    if '--no-csv' not in sys.argv:
        try:
            _csv = show.copy()
            for c in ('баланс нач', 'поп/выв', 'реализовано', 'пик ₽', 'мин ₽',
                      'закрытие ₽', 'объём@пик', '₽/лот@пик', 'поз@пик'):
                if c in _csv.columns:
                    _csv[c] = _csv[c].astype(float).round(2)
            _csv.to_csv(CSV_PATH, index=False, encoding='utf-8-sig', decimal=',')
            print("\nCSV: {}".format(CSV_PATH))
        except Exception as exc:
            print("\nCSV не записан: {!r}".format(exc))

    # --dump [ГГГГ-ММ-ДД] — выгрузить ВСЕ замеры (без фильтра выходных) в CSV
    if '--dump' in sys.argv:
        _i = sys.argv.index('--dump')
        _day = sys.argv[_i + 1] if len(sys.argv) > _i + 1 else None
        _dump(df, _day)
    _tail(df)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
