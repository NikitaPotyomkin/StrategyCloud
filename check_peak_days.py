"""Потенциал дня: equity - balance_на_начало_суток - внешние деньги суток.

Запуск:  python.exe check_peak_days.py            # таблица + journals/peak_daily.csv
         python.exe check_peak_days.py --dump      # выгрузить ВСЕ замеры в CSV
         python.exe check_peak_days.py --dump 2026-10-29
         python.exe check_peak_days.py --no-csv

Логика (та же, что в dashboard.risk_equity_block):
  bal_start = balance первого замера суток (серверное время, UTC+3);
  ext       = пополнения/выводы, пришедшие к моменту замера (накопительно за сутки);
  потенциал = equity - bal_start - ext  — сколько было бы заработано за день,
                если закрыть всё в этот момент (реализованное с начала дня + floating,
                без внешних денег);
  пик  = max(потенциала) за сутки;
  дно  = min(потенциала).

В отличие от «floating_total» (equity - balance в моменте) потенциал НЕ обнуляется
после каждого закрытия: убыточные закрытия остаются в минусе дня, поэтому
отрицательные сутки видны как отрицательный пик.

Вычет внешних денег обязателен: 29.10 пополнение +100 000 ₽ подняло balance при
старом bal_start, и «прибыль дня» без вычета показала 110 252 ₽ вместо ~6-7 тыс.

Выходные (сб/вс) в анализ не входят: рынок закрыт, сэмплер пишет одно и то же.

Колонки сверки с финстейтментом:
  поп/выв     — внешние деньги за сутки из balance_ops (cutoff/bootstrap не в счёт);
  реализовано — Δбаланса минус поп/выв = результат по ЗАКРЫТЫМ сделкам.

Историю пересчитывать не нужно: всё считается на лету из equity_samples, поэтому
старые дни появляются сразу после обновления кода/запуска скрипта.
"""

import sys

import numpy as np
import pandas as pd

import trades_db

SRV_OFFSET_H = 3     # как в risk_equity_block: серверное время = UTC+3
CSV_PATH = 'journals/peak_daily.csv'
NO_FLOW_SOURCES = ('cutoff', 'bootstrap')   # входящий остаток — не движение средств


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


def _flows_frame():
    """Внешние деньги по операциям: ts, ts_true, day, amount.

    balance_ops.ts хранится как серверное время «под видом UTC», поэтому для
    сравнения с equity_samples.ts (истинный epoch) переводим его в ts_true
    вычитанием SRV_OFFSET_H часов. День операции — серверная дата.
    """
    empty = pd.DataFrame(columns=['ts', 'ts_true', 'day', 'amount'])
    try:
        import cashflow as _cf
        rows = _cf.ops_list(limit=5000)
    except Exception as exc:
        print("  cashflow/balance_ops недоступны ({}): вычет отключён".format(exc))
        return empty

    recs = []
    for row in rows:
        try:
            _ts, amount, _kind, src = int(row[0]), float(row[1]), row[2], str(row[3] or '')
        except (TypeError, ValueError, IndexError):
            continue
        if src in NO_FLOW_SOURCES or amount == 0:
            continue
        # У разных источников balance_ops.ts в разной шкале:
        #   'deals'     — deal.time, серверное время «под видом UTC» (сдвиг +3 ч);
        #   'reconcile' — time.time(), обычный epoch (сдвига нет).
        shift = 0 if src in ('reconcile', 'manual') else SRV_OFFSET_H * 3600
        recs.append((_ts - shift, amount))
    if not recs:
        return empty

    fr = pd.DataFrame(recs, columns=['ts', 'amount'])
    fr['ts_true'] = fr['ts']          # ts уже приведён к истинному epoch
    # день операции — серверная дата (та же граница суток, что у сэмплов)
    fr['day'] = pd.to_datetime(fr['ts_true'] + SRV_OFFSET_H * 3600,
                               unit='s', utc=True).dt.date
    return fr.sort_values('ts_true').reset_index(drop=True)


def _external_flows():
    """Внешние деньги по суткам: {серверная дата: сумма ₽}."""
    flows = _flows_frame()
    out = {}
    if flows.empty:
        return out
    for day, g in flows.groupby('day'):
        out[day] = float(g['amount'].sum())
    return out


def _cum_flows(flows, day, ts_values):
    """Внешние деньги, уже пришедшие к каждому замеру (накопительно за сутки)."""
    out = np.zeros(len(ts_values), dtype=float)
    if flows is None or flows.empty:
        return out
    _f = flows[flows['day'] == day]
    if _f.empty:
        return out
    _ft = _f['ts_true'].to_numpy(dtype=float)
    _cum = np.cumsum(_f['amount'].to_numpy(dtype=float))
    _idx = np.searchsorted(_ft, np.asarray(ts_values, dtype=float), side='right') - 1
    return np.where(_idx >= 0, _cum[np.clip(_idx, 0, len(_cum) - 1)], 0.0)


def _exit_quantiles(df, out):
    """Ретро-оценка тактики «закрыть всё, когда потенциал дошёл до порога».

    Пороги берутся из распределения ДНЕВНЫХ ПИКОВ: 25% квантиль, медиана,
    75% и 90% — плюс «лучший по данным» порог из сетки (это подгонка, помечаем).
    Для дня: если порог достигнут — итог дня = потенциал в этот момент, иначе
    итог = потенциал на последнем замере суток. Выход считается окончанием дня.
    """
    empty = pd.DataFrame()
    series = [x['potential'].to_numpy(dtype=float)
              for _d, x in df.groupby('day', sort=True)
              if not bool(x['weekend'].iloc[0])]
    peaks = pd.to_numeric(out['пик ₽'], errors='coerce').dropna()
    if not series or peaks.empty:
        return empty

    def _total(thr):
        vals, fired = [], 0
        for p in series:
            hit = np.flatnonzero(p >= thr)
            if hit.size:
                vals.append(float(p[hit[0]]))
                fired += 1
            else:
                vals.append(float(p[-1]))
        return float(np.sum(vals)), fired

    base = float(pd.to_numeric(out['закрытие ₽'], errors='coerce').sum())
    rows = []
    labels = (('25% пиков', 0.25), ('медиана', 0.50),
              ('75% пиков', 0.75), ('90% пиков', 0.90))
    for name, q in labels:
        thr = float(peaks.quantile(q))
        total, fired = _total(thr)
        rows.append({'порог ₽': thr, 'опора': name, 'итог ₽': total,
                     'дней сработало': fired, 'дней всего': len(series),
                     'к факту ₽': total - base})

    # «идеальный» порог по этим же данным — верхняя граница, а не план
    lo, hi = float(peaks.min()), float(peaks.max())
    best_thr, best_total = None, float('-inf')
    if hi > lo:
        for thr in np.linspace(lo, hi, 80):
            total, _fired = _total(float(thr))
            if total > best_total:
                best_thr, best_total = float(thr), total
    if best_thr is not None:
        _t, _f = _total(best_thr)
        rows.append({'порог ₽': best_thr, 'опора': 'идеал по сетке (подгонка)',
                     'итог ₽': _t, 'дней сработало': _f,
                     'дней всего': len(series), 'к факту ₽': _t - base})

    res = pd.DataFrame(rows)
    print("\n=== тактика «закрыть всё на пороге» (ретроспектива, шаг ~5 мин) ===")
    print("факт (держим до конца дня): {:+,.0f} ₽; потолок «ровно на пике»: "
          "{:+,.0f} ₽".format(base, float(peaks.sum())))
    for _, r in res.iterrows():
        print("  порог {:>9,.0f} ₽ · {:<22} → {:>+10,.0f} ₽  ({:+,.0f} к факту, "
              "сработал {}/{} дней)".format(
                  r['порог ₽'], r['опора'], r['итог ₽'], r['к факту ₽'],
                  int(r['дней сработало']), int(r['дней всего'])))
    print("  тактика «закрыть всё ровно на пике» недостижима: пик дня известен "
          "только задним числом, поэтому строка «идеал по сетке» — подгонка.")

    try:
        _csv = res.copy()
        for c in ('порог ₽', 'итог ₽', 'к факту ₽'):
            _csv[c] = pd.to_numeric(_csv[c], errors='coerce').round(2)
        _csv.to_csv('journals/exit_quantiles.csv', index=False,
                    encoding='utf-8-sig', decimal=',')
        print("  CSV: journals/exit_quantiles.csv")
    except Exception as exc:
        print("  CSV не записан: {!r}".format(exc))
    return res


def _dump(df, day=None):
    """Выгрузка ВСЕХ замеров в CSV (Excel / DB Browser)."""
    x = df if day is None else df[df['dt'].dt.strftime('%Y-%m-%d') == day]
    if x.empty:
        print("\nнечего выгружать: замеров за {} нет".format(day or 'весь период'))
        return
    cols = {'dt': 'время_сервер', 'ts': 'epoch', 'balance': 'balance',
            'equity_': 'equity', 'floating_total': 'floating_₽', 'ext': 'внешние_₽',
            'floating_volume': 'объём_лот', 'potential': 'потенциал_₽'}
    use = [c for c in cols if c in x.columns]
    out = x.sort_values('ts')[use].rename(columns=cols)
    for c in ('floating_₽', 'equity', 'внешние_₽', 'потенциал_₽', 'объём_лот'):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors='coerce').round(2)
    path = ('journals/equity_samples_{}.csv'.format(day) if day
            else 'journals/equity_samples.csv')
    try:
        out.to_csv(path, index=False, encoding='utf-8-sig', decimal=',')
        print("\nвыгружено замеров: {} -> {}".format(len(out), path))
    except Exception as exc:
        print("\nCSV не записан: {!r}".format(exc))


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
    df['balance'] = pd.to_numeric(df['balance'], errors='coerce')
    df['floating_total'] = pd.to_numeric(df['floating_total'], errors='coerce')
    # equity берём из базы, если её нет — собираем как balance + floating
    df['equity_'] = (pd.to_numeric(df['equity'], errors='coerce') if 'equity' in df.columns
                     else df['balance'] + df['floating_total'])
    df = df[df['equity_'].notna() & df['balance'].notna()]
    df['dt'] = (pd.to_datetime(df['ts'], unit='s', utc=True)
                + pd.Timedelta(hours=SRV_OFFSET_H))
    df['day'] = df['dt'].dt.date
    df['weekend'] = df['dt'].dt.weekday >= 5
    df['vol'] = (pd.to_numeric(df['floating_volume'], errors='coerce')
                 if 'floating_volume' in df.columns
                 else pd.Series(float('nan'), index=df.index))
    df = df.sort_values('ts').reset_index(drop=True)

    # потенциал дня: equity - balance первого замера суток - внешние деньги
    _b0 = df.groupby('day')['balance'].first()
    df['bal_start'] = df['day'].map(_b0)

    flows = _flows_frame()
    df['ext'] = 0.0
    if not flows.empty:
        _ext = np.zeros(len(df), dtype=float)
        _days = df['day'].to_numpy()
        _ts = df['ts'].to_numpy(dtype=float)
        for _day in pd.unique(_days):
            _mask = _days == _day
            _ext[_mask] = _cum_flows(flows, _day, _ts[_mask])
        df['ext'] = _ext
    df['potential'] = df['equity_'] - df['bal_start'] - df['ext']

    _totals = _external_flows()

    first, last = df['dt'].min(), df['dt'].max()
    print("строк: {}   период: {} — {}   торговых дней: {}".format(
        len(df), first.strftime('%d.%m %H:%M'), last.strftime('%d.%m %H:%M'),
        df.loc[~df['weekend'], 'day'].nunique()))
    print("выходных в базе: {} суток — в расчёт не берутся".format(
        df.loc[df['weekend'], 'day'].nunique()))
    print("внешние деньги (balance_ops): {} дней, сумма {:+,.0f} ₽ — вычтены из "
          "потенциала".format(len(_totals), float(sum(_totals.values()))))

    rows = []
    for day, x in df.groupby('day', sort=True):
        weekend = bool(x['weekend'].iloc[0])
        # idxmax/idxmin возвращают МЕТКУ индекса, а не позицию: после groupby метки
        # идут подряд от исходного df, поэтому .iloc[label] падал с out-of-bounds.
        x = x.reset_index(drop=True)
        if weekend:
            continue
        i = int(x['potential'].idxmax())
        low_i = int(x['potential'].idxmin())
        m = x['vol'] > 0
        per_peak = float((x.loc[m, 'potential'] / x.loc[m, 'vol']).max()) if m.any() else float('nan')
        ext = float(_totals.get(day, 0.0))
        _vol_peak = float(x['vol'].iloc[i]) if pd.notna(x['vol'].iloc[i]) else float('nan')
        rows.append({
            'день': day,
            'замеров': len(x),
            'баланс нач': float(x['bal_start'].iloc[0]),
            'поп/выв': ext,
            'реализовано': float(x['balance'].iloc[-1] - x['bal_start'].iloc[0]) - ext,
            'пик ₽': float(x['potential'].iloc[i]),
            # для аудита: пик = equity@момент - balance@начало суток - ext
            'equity@пик': float(x['equity_'].iloc[i]),
            'balance@пик': float(x['balance'].iloc[i]),
            '75% пика': float(x['potential'].iloc[i]) * 0.75,
            # процент выполнения плана: сколько взято к концу суток от пика дня
            'забрано %': ((float(x['potential'].iloc[-1])
                           / float(x['potential'].iloc[i]) * 100.0)
                          if float(x['potential'].iloc[i]) > 0 else float('nan')),
            'время пика': x['dt'].iloc[i].strftime('%H:%M'),
            'дно ₽': float(x['potential'].iloc[low_i]),
            'время дна': x['dt'].iloc[low_i].strftime('%H:%M'),
            'закрытие ₽': float(x['potential'].iloc[-1]),
            'поз@пик': (float(x['n_positions'].iloc[i]) if 'n_positions' in x.columns
                        else float('nan')),
            'объём@пик': _vol_peak,
            '₽/лот@пик': per_peak,
            'одинак.подряд': _max_run(list(x['potential'].round(2))),
        })

    out = pd.DataFrame(rows)
    if out.empty:
        print("торговых дней в базе нет")
        return 0

    print("\n=== потенциал дня = equity - balance на начало суток - поп/выв ===")
    # equity@пик и balance@пик — только в CSV (аудит), в консоли таблица уже широкая
    _show = out.drop(columns=['equity@пик', 'balance@пик', '75% пика', 'забрано %'],
                     errors='ignore')
    print(_show.to_string(index=False,
                        formatters={'баланс нач': lambda v: '{:,.0f}'.format(v),
                                    'поп/выв': lambda v: '{:+,.0f}'.format(v),
                                    'реализовано': lambda v: '{:+,.0f}'.format(v),
                                    'пик ₽': lambda v: '{:,.0f}'.format(v),
                                    'дно ₽': lambda v: '{:,.0f}'.format(v),
                                    'закрытие ₽': lambda v: '{:,.0f}'.format(v),
                                    'объём@пик': lambda v: _f(v, 2),
                                    '₽/лот@пик': lambda v: _f(v, 0)}))

    _neg = int((out['пик ₽'] < 0).sum())
    print("\nторговых дней: {}".format(len(out)))
    print("дней с отрицательным пиком (весь день в минусе): {}".format(_neg))
    print("дней, где ВСЕ сутки были в плюсе: {}".format(int((out['дно ₽'] >= 0).sum())))
    print("дней без объёма (₽/лот не посчитать): {}".format(
        int(out['₽/лот@пик'].isna().sum())))
    print("внешние деньги за эти дни: {:+,.0f} ₽".format(float(out['поп/выв'].sum())))
    print("реализовано (сверять с финстейтментом): {:+,.0f} ₽".format(
        float(out['реализовано'].sum())))

    _exit_quantiles(df, out)

    print("\nТОП-5 пиков потенциала:")
    for _, r in out.nlargest(min(5, len(out)), 'пик ₽').iterrows():
        print("  {} {:>10,.0f} ₽ в {} · дно {:,.0f} ₽ · закрытие {:,.0f} ₽ · "
              "реализовано {:+,.0f} ₽".format(
                  r['день'], r['пик ₽'], r['время пика'], r['дно ₽'],
                  r['закрытие ₽'], r['реализовано']))

    if '--no-csv' not in sys.argv:
        try:
            _csv = out.copy()
            for c in ('баланс нач', 'поп/выв', 'реализовано', 'пик ₽', 'дно ₽',
                      'закрытие ₽', 'объём@пик', '₽/лот@пик', 'поз@пик',
                      'equity@пик', 'balance@пик', '75% пика', 'забрано %'):
                if c in _csv.columns:
                    _csv[c] = pd.to_numeric(_csv[c], errors='coerce').round(2)
            _csv.to_csv(CSV_PATH, index=False, encoding='utf-8-sig', decimal=',')
            print("\nCSV: {}".format(CSV_PATH))
        except Exception as exc:
            print("\nCSV не записан: {!r}".format(exc))

    if '--dump' in sys.argv:
        _i = sys.argv.index('--dump')
        _dump(df, sys.argv[_i + 1] if len(sys.argv) > _i + 1 else None)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
