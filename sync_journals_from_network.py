"""Скрипт синхронизации данных из сетевой папки StrategyCloud.

По умолчанию тянет:
  • journals/     — целиком (ранкинги, реестр стратегий, журнал сделок, квоты штурвала);
  • checkpoints/  — только ЛЁГКИЕ файлы состояния:
                    backtest_history.jsonl  (источник вкладки Backtest в дэшборде),
                    night_reset.json, last_full_recalc.json, last_run.json.

Тяжёлые посимвольные кэши чекпойнтов (<SYMBOL>.json) по умолчанию НЕ копируются —
для дэшборда они не нужны. Включить: --with-combos

Использование:
    python sync_journals_from_network.py
    python sync_journals_from_network.py \\\\192.168.0.106\\Users\\nikit\\PycharmProjects\\StrategyCloud
    python sync_journals_from_network.py --with-combos
    python sync_journals_from_network.py --no-checkpoints
    python sync_journals_from_network.py -y            # без интерактивного подтверждения

Путь можно задавать как к корню проекта, так и к папке journals (как раньше) —
если последний элемент пути равен 'journals', берётся его родитель.
"""
import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_NETWORK_ROOT = r"\\192.168.0.106\Users\nikit\PycharmProjects\StrategyCloud"

# Лёгкие файлы состояния из checkpoints/ — нужны дэшборду и диагностике.
CHECKPOINT_LIGHT_FILES = (
    'backtest_history.jsonl',
    'night_reset.json',
    'last_full_recalc.json',
    'last_run.json',
)


def _fmt_size(path):
    """' (12.34 MB)' для файла или '' если размер неизвестен/ноль."""
    try:
        size = float(path.stat().st_size)
    except OSError:
        return ''
    if size <= 0:
        return ''
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f' ({size:.2f} {unit})' if unit != 'B' else f' ({int(size)} B)'
        size /= 1024
    return ''


def copy_directory(src, dst, keep_files=None):
    """Копировать содержимое директории src в dst.

    keep_files — набор имён файлов для копирования (None → копировать все).
    Файлы вне набора считаются пропущенными. Подпапки копируются всегда.
    Возвращает (copied, skipped, errors).
    """
    dst.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    errors = []

    try:
        _items = sorted(os.listdir(src))
    except OSError as exc:
        # SMB-шара: Path.exists() может быть True, а листинг падать (WinError 3 —
        # «Системе не удается найти указанный путь»). Раньше это прерывало весь
        # sync: journals/ уже был скопирован, но checkpoints/ валил скрипт, и
        # вкладка Backtest так и не получала backtest_history.jsonl.
        print(f"  ✗ {src}: каталог не читается ({exc!r}) — пропуск")
        return copied, skipped, errors + [(str(src), f'listdir: {exc!r}')]
    for item in _items:
        src_path = os.path.join(src, item)
        dst_path = os.path.join(dst, item)

        if os.path.isfile(src_path):
            if keep_files is not None and item not in keep_files:
                skipped += 1
                continue
            try:
                shutil.copy2(src_path, dst_path)  # copy2 сохраняет метаданные
                copied += 1
                print(f"  ✓ {item}{_fmt_size(Path(dst_path))}")
            except Exception as e:
                errors.append((item, str(e)))
                skipped += 1
                print(f"  ✗ {item}: {e}")
        elif os.path.isdir(src_path):
            try:
                dst_path_obj = Path(dst_path)
                if dst_path_obj.exists():
                    shutil.rmtree(dst_path)
                shutil.copytree(src_path, dst_path)
                copied += 1
                print(f"  ✓ {item}/ (директория)")
            except Exception as e:
                errors.append((item, str(e)))
                skipped += 1
                print(f"  ✗ {item}/: {e}")

    return copied, skipped, errors


def _resolve_root(raw_path):
    """Принять путь к корню проекта или к папке journals (совместимость)."""
    p = Path(raw_path)
    if p.name.lower() == 'journals':
        p = p.parent
    return p


def _list_local(target_dir):
    if not target_dir.exists():
        return []
    return sorted(target_dir.iterdir(), key=lambda x: x.name)


def _print_local_state(target_dir):
    items = _list_local(target_dir)
    if not items:
        print(f"  {target_dir.name}/: (пусто)")
        return items
    print(f"  {target_dir.name}/ — локально {len(items)} объектов:")
    for item in items:
        size = _fmt_size(item) if item.is_file() else ''
        print(f"    - {item.name}{size}")
    return items


def build_parser():
    ap = argparse.ArgumentParser(
        description='Синхронизация journals/ и лёгких файлов checkpoints/ из сетевой папки.',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('network_root', nargs='?', default=DEFAULT_NETWORK_ROOT,
                    help='Путь к корню проекта StrategyCloud в сети '
                         '(или к его папке journals). По умолчанию: %(default)s')
    ap.add_argument('--with-combos', action='store_true',
                    help='Копировать и тяжёлые посимвольные кэши checkpoints/<SYMBOL>.json')
    ap.add_argument('--no-checkpoints', action='store_true',
                    help='Не трогать checkpoints/ (только journals/, как раньше)')
    ap.add_argument('-y', '--yes', action='store_true',
                    help='Не спрашивать подтверждение')
    return ap


def main():
    args = build_parser().parse_args()

    project_dir = Path(__file__).parent
    network_root = _resolve_root(args.network_root)

    targets = [('journals', network_root / 'journals', None)]
    if not args.no_checkpoints:
        keep = None if args.with_combos else set(CHECKPOINT_LIGHT_FILES)
        targets.append(('checkpoints', network_root / 'checkpoints', keep))

    print("=" * 70)
    print("  SYNCHRONIZE FROM NETWORK")
    print("=" * 70)
    print()
    print(f"  Сетевая папка:   {network_root}")
    print(f"  Локальная папка: {project_dir}")
    print()

    if not network_root.exists():
        print(f"  ⚠ Сетевая папка недоступна: {network_root}")
        print()
        print("  Возможные причины:")
        print("    1. Нет подключения к сети/VPN")
        print("    2. Путь указан неверно")
        print("    3. Нет прав доступа")
        print("=" * 70)
        return

    # Показываем план и текущее локальное состояние
    print("  План:")
    for name, src, keep in targets:
        if not src.exists():
            print(f"    • {name}/ — ⚠ в сети не найдено, будет пропущено")
            continue
        if keep is None:
            note = "все файлы" + (" (включая тяжёлые кэши)" if name == 'checkpoints' else "")
        else:
            note = f"только {len(keep)} файлов состояния"
        print(f"    • {name}/ → {project_dir / name}  [{note}]")
    print()

    print("  Текущее локальное состояние:")
    for name, _src, _keep in targets:
        _print_local_state(project_dir / name)
    print()


    print()
    print("  Копирование...")
    print()

    start_time = datetime.now()
    total_copied = 0
    total_skipped = 0
    all_errors = []

    for name, src, keep in targets:
        print(f"  ── {name}/ ──")
        if not src.exists():
            print(f"  ⚠ {src} недоступна — пропуск")
            print()
            continue
        copied, skipped, errors = copy_directory(src, project_dir / name, keep)
        total_copied += copied
        total_skipped += skipped
        all_errors.extend(errors)
        if keep is not None and skipped:
            print(f"  (пропущено {skipped} тяжёлых/непрофильных файлов)")
        print()

    elapsed = (datetime.now() - start_time).total_seconds()

    print("=" * 70)
    print("  ИТОГ")
    print("=" * 70)
    print(f"  ✓ Скопировано:     {total_copied}")
    print(f"  ✗ Ошибок:          {len(all_errors)}")
    print(f"  ⏭ Пропущено:       {total_skipped}")
    print(f"  ⏱ Время:           {elapsed:.2f} сек")
    print()

    if all_errors:
        print("  Ошибки:")
        for filename, error in all_errors:
            print(f"    - {filename}: {error}")
        print()

    if total_copied > 0:
        print("  ✅ Синхронизация завершена успешно!")
        print(f"  📁 journals: {project_dir / 'journals'}")
        if not args.no_checkpoints:
            print(f"  📁 checkpoints: {project_dir / 'checkpoints'}"
                  f"  ← вкладка Backtest читает отсюда backtest_history.jsonl")
    else:
        print("  ⚠️ Файлов не скопировано.")

    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  ⚠ Отменено пользователем.")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ✗ Ошибка: {e}")
        sys.exit(1)
