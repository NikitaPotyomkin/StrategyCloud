#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Liveness — разметка живости стратегий реестра. ТОЛЬКО разметка.

Ничего не выключает, не удаляет и не правит. Пишет два файла:
    journals/liveness.csv          — снимок на сегодня (перезаписывается)
    journals/liveness_history.csv  — накопление по датам (для «сколько дней без плана»)

Статусы (англ., как принято в проекте):
    Alive    — сделки есть, сетка реально попадает в рынок;
    Thin     — сделки есть, но сетка «заполнена» меньше THIN_FILLS (сигнал редкий);
    Silent   — ни одной сделки ни на одном символе ни в одном параметре сетки;
    Unknown  — строк этого ключа нет в чекпойнтах (не считалась этим прогоном).

Важно: Broken (падение с исключением) здесь НЕ ловится — падение превращается
в profit 0 / n_trades 0 и внешне неотличимо от Silent. Побитых ищет _check_bt.py
на синтетическом ряду; сопоставляй два отчёта: если ключ в _check_bt «ПАДАЮТ»,
его Silent-статус означает «битая», а не «немая».

Источник данных — чекпойнты ночного прогона (checkpoints/<SYMBOL>.json):
строки результатов помечены ключом реестра (r['type'] = ключ), поля
n_trades / profit пишет сам бэктест.

Запуск из папки StrategyCloud:
    .venv\\Scripts\\python.exe liveness.py
    .venv\\Scripts\\python.exe liveness.py --silent   # только список Silent
"""
import csv
import datetime
import json
import os
import sys
import time
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from strategies._registry import REGISTRY, ENABLED_BATCH   # noqa: E402

JOURNALS = os.path.join(ROOT, 'journals')
CKPT = os.path.join(ROOT, 'checkpoints')
PLAN = os.path.join(JOURNALS, 'active_state.json')
SNAP = os.path.join(JOURNALS, 'liveness.csv')
HIST = os.path.join(JOURNALS, 'liveness_history.csv')

THIN_FILLS = 0.05          # доля «заполненных» комбинаций, ниже которой сигнал редкий

COLS = ('date', 'key', 'module', 'label', 'status', 'in_plan', 'symbols',
        'combos', 'combos_filled', 'fills_pct', 'trades_total', 'trades_max',
        'profit_total')


def _blank():
    return {'symbols': set(), 'combos': 0, 'filled': 0,
            'trades': 0, 'tmax': 0, 'profit': 0.0}


def _collect():
    """{ключ реестра: агрегат по всем символам} из чекпойнтов ночного прогона."""
    per_key = defaultdict(_blank)
    if not os.path.isdir(CKPT):
        return per_key
    for fn in os.listdir(CKPT):
        if not fn.endswith('.json'):
            continue
        try:
            with open(os.path.join(CKPT, fn), 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or 'results' not in data:
            continue
        sym = fn[:-5]
        for row in data.get('results') or []:
            key = str(row.get('type') or '')
            if not key:
                continue
            d = per_key[key]
            d['symbols'].add(sym)
            d['combos'] += 1
            n = int(row.get('n_trades') or 0)
            d['trades'] += n
            d['tmax'] = max(d['tmax'], n)
            if n > 0:
                d['filled'] += 1
            d['profit'] += float(row.get('profit') or 0.0)
    return per_key


def _plan_aliases():
    """Ключи/ярлыки, которые сейчас в дневном плане (journals/active_state.json)."""
    try:
        with open(PLAN, 'r', encoding='utf-8') as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        return set()
    out = set()
    for item in state.get('strategies') or []:
        t = str(item.get('type') or '')
        if t:
            out.add(t)
    return out


def _native_rows(per_key, plan, today):
    """Строки живости для нативных семейств: их ключей нет в ENABLED_BATCH."""
    out = []
    # Нативные семейства: в чекпойнте они помечены ИМЕНЕМ СЕМЕЙСТВА ('stoch',
    # 'skewness', ...), в ENABLED_BATCH их нет. Без этого блока у native-строк
    # Roadmap колонка Alive всегда была бы «—».
    _known = set(ENABLED_BATCH)
    for key in sorted(per_key):
        if key in _known:
            continue
        d = per_key[key]
        out.append({
            'date': today,
            'key': key,
            'module': '',
            'label': key,
            'status': _status(d),
            'in_plan': 'yes' if key in plan else 'no',
            'symbols': len(d['symbols']),
            'combos': d['combos'],
            'combos_filled': d['filled'],
            'fills_pct': round(d['filled'] / d['combos'], 3) if d['combos'] else 0.0,
            'trades_total': d['trades'],
            'trades_max': d['tmax'],
            'profit_total': round(d['profit'], 2),
        })
    return out


def _status(d):
    if not d['combos']:
        return 'Unknown'
    if d['trades'] <= 0:
        return 'Silent'
    if (d['filled'] / d['combos']) < THIN_FILLS:
        return 'Thin'
    return 'Alive'


def _rows(per_key, plan):
    today = datetime.date.today().isoformat()
    out = []
    for key in ENABLED_BATCH:
        ent = REGISTRY.get(key) or {}
        d = per_key.get(key) or _blank()
        label = str(ent.get('label') or '')
        in_plan = bool({key, label} & plan)
        out.append({
            'date': today,
            'key': key,
            'module': str(ent.get('module') or ''),
            'label': label,
            'status': _status(d),
            'in_plan': 'yes' if in_plan else 'no',
            'symbols': len(d['symbols']),
            'combos': d['combos'],
            'combos_filled': d['filled'],
            'fills_pct': round(d['filled'] / d['combos'], 3) if d['combos'] else 0.0,
            'trades_total': d['trades'],
            'trades_max': d['tmax'],
            'profit_total': round(d['profit'], 2),
        })
    out += _native_rows(per_key, plan, today)
    return out


def _write(path, rows):
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        wr = csv.DictWriter(fh, fieldnames=COLS)
        wr.writeheader()
        for r in rows:
            wr.writerow({c: r[c] for c in COLS})


def _append_history(rows):
    """Добавить сегодняшний срез к истории, заменив запись этого же дня."""
    today = rows[0]['date'] if rows else datetime.date.today().isoformat()
    old = []
    if os.path.exists(HIST):
        try:
            with open(HIST, 'r', encoding='utf-8', newline='') as fh:
                old = [r for r in csv.DictReader(fh) if r.get('date') != today]
        except OSError:
            old = []
    with open(HIST, 'w', encoding='utf-8', newline='') as fh:
        wr = csv.DictWriter(fh, fieldnames=COLS)
        wr.writeheader()
        for r in old:
            wr.writerow({c: r.get(c, '') for c in COLS})
        for r in rows:
            wr.writerow({c: r[c] for c in COLS})


def ensure_snapshot(max_age_sec: float = 6 * 3600, verbose: bool = False) -> bool:
    """Обновить journals/liveness.csv, если снимка нет или он старше max_age_sec.

    Вызывается из roadmap_build.refresh() — то есть сама, по циклу. Руками
    запускать не нужно. Стоимость: разбор чекпойнтов (7 файлов по ~13 МБ)
    только когда снимок протух, а не на каждую пересборку Roadmap.
    """
    try:
        age = time.time() - os.path.getmtime(SNAP)
    except OSError:
        age = None
    if age is not None and age < float(max_age_sec):
        return False
    rows = _rows(_collect(), _plan_aliases())
    os.makedirs(JOURNALS, exist_ok=True)
    _write(SNAP, rows)
    _append_history(rows)
    if verbose:
        cnt = defaultdict(int)
        for r in rows:
            cnt[r['status']] += 1
        print(f"  [LIVENESS] снимок обновлён: {len(rows)} стратегий ("
              + ', '.join(f"{k} {cnt[k]}" for k in ('Alive', 'Thin', 'Silent', 'Unknown'))
              + ')', flush=True)
    return True


def main():
    only_silent = '--silent' in sys.argv
    rows = _rows(_collect(), _plan_aliases())
    os.makedirs(JOURNALS, exist_ok=True)
    _write(SNAP, rows)
    if not only_silent:
        _append_history(rows)

    cnt = defaultdict(int)
    for r in rows:
        cnt[r['status']] += 1

    print(f"стратегий в батче: {len(rows)} | "
          + ' | '.join(f"{k} {cnt[k]}" for k in ('Alive', 'Thin', 'Silent', 'Unknown')))
    print()

    for st in ('Silent', 'Unknown'):
        _list = [r for r in rows if r['status'] == st]
        if not _list:
            continue
        print(f"=== {st} ({len(_list)}) ===")
        for r in _list:
            print(f"  {r['key']:32s} combos {r['combos']:3d} trades {r['trades_total']}")
        print()

    thin = [r for r in rows if r['status'] == 'Thin']
    if thin:
        print(f"=== Thin ({len(thin)}) — сигнал есть, но редкий (fills < {THIN_FILLS:.0%}) ===")
        for r in sorted(thin, key=lambda x: x['fills_pct']):
            print(f"  {r['key']:32s} fills {r['fills_pct']:.0%} "
                  f"trades {r['trades_total']:4d} combos {r['combos']}")
        print()

    print(f"снимок: {SNAP}")
    print(f"история: {HIST}")
    print("Помни: Silent у ключа из списка _check_bt.py «ПАДАЮТ» = битая, а не немая.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
