"""Отчёт по клонам реестра: какой ключ из группы реально живёт в системе.

Клон — это несколько ключей реестра на ОДИН модуль (один и тот же расчёт под
разными именами). Чем это мешает:
  * max_per_type считается по ключу, поэтому копии получают отдельные квоты;
  * штурвал (steering_quotas.json) взвешивает копии по отдельности — один и тот
    же сигнал получает 2-3x вес;
  * ночной пересчёт гоняет один модуль несколько раз с разными сетками.

Отчёт по каждому ключу группы показывает:
  * сетку параметров, min_len и label;
  * сколько раз ключ встречается в steering_quotas.json (вес в штурвале);
  * сколько строк в strategy_registry.csv (сколько раз активировался) и с какой даты.

Только чтение. Запуск: python tools/clone_report.py
"""
import csv
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
JOURNALS = os.path.join(ROOT, 'journals')

sys.path.insert(0, ROOT)


def load_quotas(registry):
    """Сколько раз ключ фигурирует в steering_quotas.json (ключ там = символ + '_' + ключ)."""
    quotas = Counter()
    path = os.path.join(JOURNALS, 'steering_quotas.json')
    if not os.path.exists(path):
        return quotas
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    for quota_key in data:
        for key in registry:
            if quota_key.endswith('_' + key):
                quotas[key] += 1
                break
    return quotas


def load_activations():
    """Сколько раз ключ активировался (колонка type) и с какой даты."""
    active, first_seen = Counter(), {}
    path = os.path.join(JOURNALS, 'strategy_registry.csv')
    if not os.path.exists(path):
        return active, first_seen
    with open(path, encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            key = (row.get('type') or '').strip()
            if not key:
                continue
            active[key] += 1
            stamp = (row.get('activated_at') or '')[:10]
            if stamp and (key not in first_seen or stamp < first_seen[key]):
                first_seen[key] = stamp
    return active, first_seen


def main():
    from strategies import _registry as r

    quotas = load_quotas(r.REGISTRY)
    active, first_seen = load_activations()

    modules = defaultdict(list)
    for key, spec in r.REGISTRY.items():
        modules[spec.get('module') or key].append(key)

    clones = {mod: sorted(keys) for mod, keys in modules.items() if len(keys) > 1}
    extra = sum(len(keys) - 1 for keys in clones.values())
    print(f"групп клонов: {len(clones)}, лишних ключей: {extra}")
    print("квот — сколько раз ключ есть в штурвале; активаций — строк в strategy_registry.csv\n")

    suggest = {}
    for mod in sorted(clones):
        print(mod)
        for key in clones[mod]:
            spec = r.REGISTRY[key]
            grid = spec.get('grid') or []
            print(f"  {key:26s} grid={str(grid):20s} min_len={str(spec.get('min_len')):4s} "
                  f"label={str(spec.get('label')):10s} "
                  f"квот={quotas.get(key, 0)} активаций={active.get(key, 0)} "
                  f"с {first_seen.get(key, '-')}")
        best = max(
            clones[mod],
            key=lambda k: (quotas.get(k, 0), active.get(k, 0),
                           len(r.REGISTRY[k].get('grid') or [])),
        )
        suggest[best] = clones[mod]
        print(f"  -> предлагаю оставить: {best}\n")

    print("Итого предлагается удалить ключей:", extra)
    for keep, keys in sorted(suggest.items()):
        drop = [k for k in keys if k != keep]
        print(f"  оставить {keep:26s} удалить: {', '.join(drop)}")

    silent = [k for k in r.REGISTRY if not quotas.get(k) and not active.get(k)]
    print(f"\nключей без квот и без активаций (всего {len(silent)}):")
    for key in sorted(silent):
        print(f"  {key}")


if __name__ == '__main__':
    main()
