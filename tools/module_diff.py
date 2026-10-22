"""Сверка состава модулей strategies/*.py с их бэкапами (.bak.<ts>).

Зачем: компиляция ловит только синтаксис, а поведенческие гейты
(calc_vector_parity / loop_parity / bt_split) вызывают функции по именам — поэтому
потеря МОДУЛЬНОГО имени (алиас ``check_entry = check_entry_xxx``, константа, функция)
проходит мимо всех гейтов, но ломает ``import main`` (ImportError на старте).

Инструмент загружает текущий модуль и его последний бэкап и сравнивает набор
модульных имён. «ПОТЕРЯНО» — критично: где-то пропало имя, которое кто-то импортирует.

Запуск:
    python tools/module_diff.py                # все модули, у которых есть бэкап
    python tools/module_diff.py --module macd_cross
    python tools/module_diff.py --verbose      # печатать и добавленные имена (и ok)

Код возврата 1, если есть хоть одна потеря.
"""
import argparse
import importlib.machinery
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRAT = os.path.join(ROOT, 'strategies')
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def latest_bak(name):
    """Самый свежий strategies/<name>.py.bak.<ts> (None, если бэкапа нет)."""
    baks = sorted(f for f in os.listdir(STRAT) if f.startswith(name + '.py.bak.'))
    return os.path.join(STRAT, baks[-1]) if baks else None


def load_backup(name, bak):
    """Старая копия модуля: .bak.<ts> не .py, поэтому загрузчик задаём явно."""
    mod_name = f'strategies.{name}__bak'
    loader = importlib.machinery.SourceFileLoader(mod_name, bak)
    spec = importlib.util.spec_from_loader(mod_name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    loader.exec_module(module)
    return module


def public_names(mod):
    return {n for n in vars(mod) if not n.startswith('__')}


def main():
    ap = argparse.ArgumentParser(description='Сверка модульных имён strategies/*.py с бэкапами')
    ap.add_argument('--module', default=None, help='один модуль (имя файла без .py)')
    ap.add_argument('--verbose', action='store_true', help='печатать добавленные имена и ok')
    args = ap.parse_args()

    files = sorted(f[:-3] for f in os.listdir(STRAT)
                   if f.endswith('.py') and f != '__init__.py')
    if args.module:
        files = [args.module]

    checked = 0
    bad = 0
    skipped = []
    for name in files:
        bak = latest_bak(name)
        if not bak:
            skipped.append(name)
            continue
        try:
            cur = __import__(f'strategies.{name}', fromlist=['*'])
        except Exception as exc:
            print(f'{name:28s} ОШИБКА ИМПОРТА (текущий): {exc!r}')
            bad += 1
            continue
        try:
            old = load_backup(name, bak)
        except Exception as exc:
            print(f'{name:28s} ОШИБКА ИМПОРТА (бэкап): {exc!r}')
            bad += 1
            continue

        cur_names = public_names(cur)
        old_names = public_names(old)
        missing = sorted(old_names - cur_names)
        added = sorted(cur_names - old_names)
        checked += 1

        if missing:
            bad += 1
            print(f'{name:28s} ПОТЕРЯНО: {", ".join(missing)}')
            print(f'{"":28s}   бэкап: {os.path.basename(bak)}')
        elif args.verbose:
            tail = f'   + {", ".join(added)}' if added else ''
            print(f'{name:28s} ok{tail}')

    print(f'\nПроверено модулей: {checked}; с потерями: {bad}; без бэкапа: {len(skipped)}')
    if skipped:
        print('Без бэкапа: ' + ', '.join(skipped))
    if bad:
        print('\nЧто делать: сравнить потерянные имена с бэкапом и вернуть их в модуль '
              '(это ровно тот класс ошибок, который не видят паритет и компиляция).')
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
