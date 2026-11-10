"""Симуляция схем фиксации прибыли дня по истории (READ-ONLY).

Сравнивает за N дней три схемы:
  A. без фиксации     — результат дня = последний потенциал дня;
  B. плоский трим     — срез, когда потенциал дня >= pct * эталон * план;
  C. трейлинг от пика — активация при потенциале >= act * эталон * план,
                        срез при откате от пика дня на trail (доля пика).

Потенциал дня(t) = реализованный P&L сделок дня к t + floating_total(t).
План дня         = максимум floating_volume за день (как peak_trim._daily_per_lot).
Эталон дня       = медиана пиковых ₽/лот по дням ДО этого дня (как _daily_ref,
                   lookback_days=0, ref_quantile=0.50).

Модель среза: закрываем (1 - keep) объёма и фиксируем (1 - keep) плавающей,
остаток keep ловит keep последующего движения до конца дня. Это приближение
реального трима (закрытие каждого объёма до keep_volume=0.01).

База открывается в режиме readonly: ничего не пишется, торговля не затрагивается.

Запуск (из папки StrategyCloud):
    python peak_trim_sim.py --days 30
    python peak_trim_sim.py --days 60 --pct 2.0 --act 2.0 --trail 0.20
"""

import argparse
import bisect
import datetime
import os
import sqlite3
import statistics

SRV_OFFSET_H = 3


def _day_of_ts(ts):
    """Серверный день (UTC+3) для истинного epoch ts."""
    return datetime.datetime.fromtimestamp(
        int(ts) + SRV_OFFSET_H * 3600, datetime.timezone.utc).strftime('%Y-%m-%d')


def _cum(pairs):
    """[(ts, net)] -> [(ts, накопленный net)] по возрастанию времени."""
    out, run = [], 0.0
    for ts, net in sorted(pairs):
        run += net
        out.append((ts, run))
    return out


def _realized_at(tss, cum, ts):
    """Реализованный P&L дня к моменту ts."""
    if not cum:
        return 0.0
    i = bisect.bisect_right(tss, int(ts)) - 1
    return cum[i][1] if i >= 0 else 0.0


def _load(con, login=None):
    con.row_factory = sqlite3.Row
    samples, deals = {}, {}
    for r in con.execute(
            "SELECT ts, floating_total, floating_volume, account_login "
            "FROM equity_samples ORDER BY ts"):
        if login and r['account_login'] not in (None, login):
            continue
        d = _day_of_ts(r['ts'])
        samples.setdefault(d, []).append(
            (int(r['ts']), float(r['floating_total'] or 0.0),
             float(r['floating_volume'] or 0.0)))
    for r in con.execute(
            "SELECT time, profit, commission, swap, fee, account_login "
            "FROM deals WHERE deal_type IN (0, 1) ORDER BY time"):
        if login and r['account_login'] not in (None, login):
            continue
        ts = int(r['time']) - SRV_OFFSET_H * 3600
        net = (float(r['profit'] or 0.0) + float(r['commission'] or 0.0)
               + float(r['swap'] or 0.0) + float(r['fee'] or 0.0))
        deals.setdefault(_day_of_ts(ts), []).append((ts, net))
    return samples, deals


def _sim(series, idx, keep):
    """Результат дня при срезе в точке idx (доля keep остаётся в рынке)."""
    _ts, pot, real, fl = series[idx]
    final = series[-1][1]
    return (real + (1.0 - keep) * fl) + keep * (final - pot)


def _find_flat(series, threshold):
    for i, (_ts, pot, _r, _f) in enumerate(series):
        if pot >= threshold:
            return i
    return None


def _find_trail(series, act, trail):
    """Индекс срабатывания трейлинга: откат от пика после активации."""
    started, peak = False, None
    for i, (_ts, pot, _r, _f) in enumerate(series):
        if not started:
            if pot >= act:
                started, peak = True, pot
            continue
        if pot > peak:
            peak = pot
            continue
        if pot <= peak * (1.0 - trail):
            return i
    return None


def main():
    ap = argparse.ArgumentParser(description='Симуляция схем фиксации прибыли дня')
    ap.add_argument('--days', type=int, default=30, help='сколько последних дней показать')
    ap.add_argument('--db', default=os.path.join('journals', 'trades.db'))
    ap.add_argument('--pct', type=float, default=1.0, help='порог плоского трима, долей эталона')
    ap.add_argument('--act', type=float, default=2.0, help='порог активации трейлинга, долей эталона')
    ap.add_argument('--trail', type=float, default=0.20, help='откат от пика для среза, доля')
    ap.add_argument('--keep', type=float, default=0.10, help='доля объёма, которая остаётся')
    ap.add_argument('--login', type=int, default=None)
    a = ap.parse_args()

    if not os.path.exists(a.db):
        print(f'  нет базы: {a.db}')
        return 1
    con = sqlite3.connect('file:' + os.path.abspath(a.db).replace(os.sep, '/') + '?mode=ro', uri=True)
    try:
        samples, deals = _load(con, a.login)
    finally:
        con.close()

    # --- ряд по дням: план, реализации, потенциал ---
    info = {}
    for d in sorted(samples):
        rows = samples[d]
        plan = max((v for _t, _f, v in rows), default=0.0) if rows else 0.0
        if plan < 0.10:
            continue
        cum = _cum(deals.get(d, []))
        tss = [p[0] for p in cum]
        series = []
        for ts, fl, _v in rows:
            real = _realized_at(tss, cum, ts)
            series.append((ts, real + fl, real, fl))
        if len(series) < 10:
            continue
        peak = max(p[1] for p in series)
        info[d] = {'plan': plan, 'series': series, 'peak': peak,
                   'per_lot': peak / plan, 'final': series[-1][1]}

    days = sorted(info)
    if not days:
        print('  нет данных в equity_samples')
        return 1

    # --- эталон: медиана пиковых ₽/лот по дням ДО текущего ---
    for i, d in enumerate(days):
        prev = [info[x]['per_lot'] for x in days[:i]]
        info[d]['ref'] = statistics.median(prev) if prev else None

    show = [d for d in days if info[d]['ref']]
    show = show[-a.days:]

    print(f'  схемы: B = плоский {a.pct:.2f}x эталона | '
          f'C = трейлинг act {a.act:.2f}x, откат {a.trail:.0%}, keep {a.keep:.0%}')
    print(f'  {"день":<12}{"план":>7}{"эталон":>9}{"пик":>10}{"финал":>10}'
          f'{"просад":>9}{"A_без":>10}{"B_плоск":>10}{"C_трейл":>10}')
    tot = {'A': 0.0, 'B': 0.0, 'C': 0.0}
    n_b = n_c = 0
    for d in show:
        v = info[d]
        ref, plan, series = v['ref'], v['plan'], v['series']
        final = v['final']
        peak = v['peak']
        low_after = min(p[1] for p in series[series.index(max(series, key=lambda q: q[1])):])
        dd = low_after - peak

        i_b = _find_flat(series, a.pct * ref * plan)
        i_c = _find_trail(series, a.act * ref * plan, a.trail)
        r_b = _sim(series, i_b, a.keep) if i_b is not None else final
        r_c = _sim(series, i_c, a.keep) if i_c is not None else final
        if i_b is not None:
            n_b += 1
        if i_c is not None:
            n_c += 1
        tot['A'] += final
        tot['B'] += r_b
        tot['C'] += r_c
        print(f'  {d:<12}{plan:>7.2f}{ref:>9,.0f}{peak:>10,.0f}{final:>10,.0f}'
              f'{dd:>9,.0f}{final:>10,.0f}{r_b:>10,.0f}{r_c:>10,.0f}')

    n = len(show)
    print(f'\n  дней: {n} | срез B сработал: {n_b} | срез C сработал: {n_c}')
    print(f'  ИТОГО  A без фиксации : {tot["A"]:>12,.0f} ₽')
    print(f'         B плоский трим : {tot["B"]:>12,.0f} ₽   ({tot["B"] - tot["A"]:+,.0f} к A)')
    print(f'         C трейлинг     : {tot["C"]:>12,.0f} ₽   ({tot["C"] - tot["A"]:+,.0f} к A)')
    if n:
        print(f'  средний день: A {tot["A"] / n:,.0f} | B {tot["B"] / n:,.0f} | '
              f'C {tot["C"] / n:,.0f} ₽')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
