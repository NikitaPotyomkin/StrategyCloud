"""Сборка таблицы Roadmap в SQL — то, что раньше дашборд делал при каждом рендере.

Раскладка по модулям:
  roadmap_scan.py   — счёт инвентаризации (файлы strategies/, реестр, снимки из БД);
  roadmap_store.py  — таблицы roadmap_rows / roadmap_meta в journals/trades.db;
  roadmap_build.py  — этот файл: scan() + save() одной функцией refresh();
  roadmap_tab.py    — только читает SQL, тяжёлой работы в дэше больше нет.

Кто вызывает refresh():
  • торговый цикл main.py — раз в ROADMAP_REFRESH_SEC (после рендеров не нужно,
    стоимость — только чтение файлов, ~0.1–0.5 с);
  • руками: python roadmap_build.py (разово наполнить таблицу или после деплоя);
  • кнопкой «↻ Пересчитать» во вкладке Roadmap (только при пустой/старой таблице).

Примеры:
  python roadmap_build.py            # собрать и записать
  python roadmap_build.py --print    # собрать, показать сводку, тоже записать
"""

from __future__ import annotations

import argparse
import time

# Периодичность обновления из торгового цикла (сек). Инвентаризация меняется
# только деплоем, поэтому редко: 30 мин достаточно и дёшево.
ROADMAP_REFRESH_SEC = 1800


def refresh(path=None, verbose: bool = True) -> int:
    """Пересчитать инвентаризацию и записать её в SQL. Возвращает число строк."""
    t0 = time.time()
    try:
        import roadmap_scan
        rows, stat = roadmap_scan.scan()
    except Exception as exc:
        if verbose:
            print(f"  [ROADMAP] скан не выполнен: {exc!r}", flush=True)
        return 0
    if not rows:
        if verbose:
            print("  [ROADMAP] пусто: папка strategies/ недоступна", flush=True)
        return 0
    try:
        import roadmap_store
        n = roadmap_store.save(rows, stat, path=path, verbose=verbose)
    except Exception as exc:
        if verbose:
            print(f"  [ROADMAP] запись в SQL не удалась: {exc!r}", flush=True)
        return 0
    if verbose:
        print(f"  [ROADMAP] {n} модулей за {time.time() - t0:.1f} c "
              f"(реестр {stat.get('reg', 0)}, native {stat.get('native', 0)}, "
              f"в плане {stat.get('plan', 0)})", flush=True)
    return n


def needs_refresh(path=None, max_age_sec: int = ROADMAP_REFRESH_SEC) -> bool:
    """Пора ли пересобирать: таблицы нет, она пуста или старше max_age_sec."""
    try:
        import roadmap_store
    except Exception:
        return False
    _rows, _stat, saved_at = roadmap_store.load(path)
    if not _rows or not saved_at:
        return True
    age = roadmap_store.age_sec(path)
    return (age is None) or (age >= float(max_age_sec))


def main():
    ap = argparse.ArgumentParser(description='Roadmap: инвентаризация strategies/ → SQL')
    ap.add_argument('--db', default=None, help='путь к trades.db (по умолчанию journals/trades.db)')
    ap.add_argument('--print', dest='show', action='store_true',
                    help='показать сводку по слоям после записи')
    args = ap.parse_args()
    n = refresh(path=args.db)
    if args.show and n:
        try:
            import roadmap_store
            rows, stat, saved_at = roadmap_store.load(args.db)
        except Exception:
            rows, stat, saved_at = [], {}, ''
        print(f"  собрано: {saved_at} · строк {len(rows)}")
        for k in ('files', 'reg', 'enabled', 'native', 'plan', 'gap',
                  'in_run', 'ready', 'n_score', 'combos'):
            if k in stat:
                print(f"    {k:<10} {stat[k]}")
    return 0 if n else 1


if __name__ == '__main__':
    raise SystemExit(main())
