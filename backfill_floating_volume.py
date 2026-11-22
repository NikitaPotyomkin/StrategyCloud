"""Разовый бэкфилл equity_samples.floating_volume из истории сделок.

Зачем: удельная «максимальная прибыль за день» = max(floating_total / floating_volume),
а колонка объёма появилась только 28.10.2026. Восстанавливаем объём открытых
позиций на КАЖДЫЙ замер задним числом из таблицы deals.

Как считается:
  сделка entry=IN  (0) — открытие: +volume
  сделка entry=OUT (1) — закрытие:  −volume   (частичные закрытия тоже корректны)
  накопленная сумма событий, отсортированных по времени, = открытый объём в момент t;
  для замера берём последнее событие с time <= t (0, если событий ещё не было).

ВРЕМЯ: deals.time — серверное время «как UTC» (обычно +3 ч к истинному epoch),
equity_samples.ts — истинный epoch. Поэтому к замеру прибавляется SRV_OFFSET_H.

Запуск:
    python.exe backfill_floating_volume.py            # только показать (ничего не пишет)
    python.exe backfill_floating_volume.py --write    # записать в базу
"""

import sys

import numpy as np
import pandas as pd

import trades_db

SRV_OFFSET_H = 3      # серверное время = UTC+3 (как в risk_equity_block)


def _open_volume_at(sample_ts: np.ndarray, deals: pd.DataFrame) -> np.ndarray:
    """Открытый объём (лоты) на каждый ts из sample_ts."""
    d = deals.copy()
    d['t'] = pd.to_numeric(d['time'], errors='coerce')
    d['v'] = pd.to_numeric(d['volume'], errors='coerce')
    d['e'] = pd.to_numeric(d['entry'], errors='coerce')
    d = d.dropna(subset=['t', 'v', 'e'])
    d = d[(d['v'] > 0) & d['e'].isin([0, 1, 2])]
    if d.empty:
        return np.zeros(len(sample_ts))
    d['delta'] = np.where(d['e'] == 0, d['v'], np.where(d['e'] == 1, -d['v'], d['v']))
    d = d.sort_values('t')
    ev_t = d['t'].to_numpy(dtype=np.int64)
    cum = np.cumsum(d['delta'].to_numpy(dtype=float))
    idx = np.searchsorted(ev_t, sample_ts, side='right') - 1
    out = np.where(idx >= 0, cum[np.clip(idx, 0, len(cum) - 1)], 0.0)
    return np.maximum(out, 0.0)


def main():
    write = '--write' in sys.argv[1:]
    con = trades_db.connect()
    try:
        deals = pd.read_sql(
            "SELECT time, entry, volume FROM deals WHERE entry IN (0,1,2)", con)
        eq = pd.read_sql(
            "SELECT ts, account_login, floating_total, floating_volume "
            "FROM equity_samples ORDER BY ts", con)
        if eq.empty:
            print("equity_samples пуст")
            return 0
        print(f"сделок: {len(deals)}, замеров: {len(eq)}, "
              f"из них без объёма: {int(eq['floating_volume'].isna().sum())}")

        sample_ts = pd.to_numeric(eq['ts'], errors='coerce').fillna(0).to_numpy(dtype=np.int64)
        vol = _open_volume_at(sample_ts + SRV_OFFSET_H * 3600, deals)
        eq['vol_calc'] = vol
        eq['dt'] = (pd.to_datetime(sample_ts, unit='s', utc=True)
                    + pd.Timedelta(hours=SRV_OFFSET_H))
        eq['day'] = eq['dt'].dt.date

        fl = pd.to_numeric(eq['floating_total'], errors='coerce')
        eq['per_lot'] = (fl / eq['vol_calc']).where(eq['vol_calc'] > 0)

        rows = []
        for day, g in eq.groupby('day', sort=True):
            rows.append({
                'день': day,
                'замеров': len(g),
                'с объёмом': int((g['vol_calc'] > 0).sum()),
                'max ₽/лот': g['per_lot'].max(),
                'min ₽/лот': g['per_lot'].min(),
            })
        out = pd.DataFrame(rows)
        print(out.to_string(index=False))
        print(f"\nдней с восстановленным объёмом: "
              f"{int((out['с объёмом'] > 0).sum())} из {len(out)}")

        if not write:
            print("\nрежим просмотра: в базу НИЧЕГО не записано. "
                  "Для записи добавь --write")
            return 0

        upd = eq[eq['vol_calc'] > 0][['ts', 'account_login', 'vol_calc']]
        changed = 0
        con.executemany(
            "UPDATE equity_samples SET floating_volume = ? "
            "WHERE ts = ? AND IFNULL(account_login, 0) = IFNULL(?, 0) "
            "AND floating_volume IS NULL",
            [(float(r.vol_calc), int(r.ts),
              None if pd.isna(r.account_login) else int(r.account_login))
             for r in upd.itertuples()])
        changed = con.total_changes
        con.commit()
        print(f"\nзаписано строк: {changed} "
              f"(только те, где floating_volume был NULL)")
    finally:
        con.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
