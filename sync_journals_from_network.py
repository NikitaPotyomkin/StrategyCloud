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
import json
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
    'deploy_status.json',
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


def _diag_dir(path):
    """Почему каталог не листается: путь, ссылка/джанкшн, содержимое родителя."""
    p = str(path)
    try:
        print(f"    isdir={os.path.isdir(p)} lexists={os.path.lexists(p)}")
    except OSError:
        pass
    try:
        target = os.readlink(p)
        print(f"    это ссылка/джанкшн → {target}")
    except OSError:
        pass
    try:
        parent = os.path.dirname(p)
        names = sorted(os.listdir(parent))
        shown = ', '.join(names[:15])
        print(f"    в родителе {parent}: {shown}{' …' if len(names) > 15 else ''}")
    except OSError:
        pass


def _copy_named_files(src, dst, names):
    """Точечное копирование по именам — когда листинг каталога недоступен.

    Возвращает (copied, errors). Отсутствующие файлы тихо пропускаются:
    на боевой машине какие-то из них могут быть ещё не созданы.
    """
    copied = 0
    errors = []
    for name in names:
        src_path = os.path.join(str(src), name)
        dst_path = os.path.join(str(dst), name)
        try:
            if not os.path.isfile(src_path):
                continue
            if name.endswith('.jsonl'):
                _n = _merge_jsonl(src_path, dst_path)
                print(f"  ✓ {name}: слито {_n} строк{_fmt_size(Path(dst_path))}")
            else:
                shutil.copy2(src_path, dst_path)
                print(f"  ✓ {name}{_fmt_size(Path(dst_path))}")
            copied += 1
        except Exception as e:
            errors.append((name, str(e)))
            print(f"  ✗ {name}: {e}")
    return copied, errors


def _fallback_no_listing(src, dst, keep_files, exc, copied, skipped, errors):
    """Каталог не листается (SMB-джанкшн / WinError 3) — тянем файлы по именам.

    journals/ и checkpoints/ живут в одной шаре, но checkpoints может быть
    джанкшном на другой диск: exists() → True, а listdir падает «путь не найден».
    Прямое чтение по имени при этом обычно работает, поэтому лёгкие файлы
    состояния пробуем забрать вслепую — дэшборду нужен backtest_history.jsonl.
    """
    print(f"  ✗ {src}: каталог не читается ({exc!r})")
    _diag_dir(src)
    if not keep_files:
        return copied, skipped, errors + [(str(src), f'listdir: {exc!r}')]
    print("  ↳ пробую точечно по именам (листинг недоступен, файлы могут читаться):")
    _copied, _errs = _copy_named_files(src, dst, keep_files)
    copied += _copied
    if _copied:
        return copied, skipped, errors
    errors.extend(_errs)
    return copied, skipped, errors + [(str(src), f'listdir: {exc!r}')]


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
        return _fallback_no_listing(src, dst, keep_files, exc, copied, skipped, errors)
        # Диагностика и точечное копирование по именам — внутри _fallback_no_listing.
    for item in _items:
        src_path = os.path.join(src, item)
        dst_path = os.path.join(dst, item)

        if os.path.isfile(src_path):
            if keep_files is not None and item not in keep_files:
                skipped += 1
                continue
            try:
                if item.endswith('.jsonl'):
                    # Журналы СЛИВАЕМ, а не затираем: copy2 уничтожал локальную
                    # историю прогонов, если в сети строк было меньше.
                    _n = _merge_jsonl(src_path, dst_path)
                    copied += 1
                    print(f"  ✓ {item}: слито {_n} строк{_fmt_size(Path(dst_path))}")
                    continue
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


def _merge_jsonl(src_path, dst_path):
    """Слить журнал прогонов из сети с локальным, а не затирать его.

    backtest_history.jsonl копился раньше через shutil.copy2, то есть локальная
    история полностью заменялась сетевой. Если на боевой машине строк меньше
    (журнал почистили или он только появился), здесь история исчезала.
    Здесь объединяем по ключу (ts, kind) и пишем по времени — потери нет.
    """
    recs = {}
    for path in (dst_path, src_path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    recs[(str(obj.get('ts') or ''), str(obj.get('kind') or 'none'))] = obj
        except OSError:
            continue
    if not recs:
        return 0
    tmp = str(dst_path) + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        for key in sorted(recs):
            f.write(json.dumps(recs[key], ensure_ascii=False) + '\n')
    os.replace(tmp, dst_path)
    return len(recs)


def _history_summary():
    """Сводка по ЛОКАЛЬНОМУ backtest_history.jsonl после синка.

    Нужна, чтобы «на графике ничего не появилось» не разбиралось вслепую: сразу видно,
    сколько строк, какие kind и какой последний прогон приехал с боевой машины.
    """
    path = Path(__file__).parent / 'checkpoints' / 'backtest_history.jsonl'
    if not path.exists():
        return f"  📓 backtest_history.jsonl: файла нет — {path}"
    kinds, last_ts, total = {}, '', 0
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(obj, dict):
                    continue
                total += 1
                kk = str(obj.get('kind') or 'none')
                kinds[kk] = kinds.get(kk, 0) + 1
                ts = str(obj.get('ts') or '')
                if ts > last_ts:
                    last_ts = ts
    except OSError as exc:
        return f"  📓 backtest_history.jsonl: не читается ({exc!r})"
    parts = ', '.join(f"{k}={v}" for k, v in sorted(kinds.items()))
    return (f"  📓 backtest_history.jsonl: строк {total}"
            f"{' (' + parts + ')' if parts else ''}; "
            f"последний прогон {last_ts or '—'}")


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
    ap.add_argument('--checkpoints-dir', default=None,
                    help='Свой путь к checkpoints/ в сети (если на боевой машине это '
                         'джанкшн/другой диск). Пример: \\\\192.168.0.106\\d$\\StrategyCloud\\checkpoints')
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
        ckpt_src = (Path(args.checkpoints_dir) if args.checkpoints_dir
                    else network_root / 'checkpoints')
        targets.append(('checkpoints', ckpt_src, keep))

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

    # Страховка: бот дублирует журнал прогонов в journals/. Если checkpoints/ в сети
    # недоступен (джанкшн на другой диск), история прогонов приезжает оттуда.
    _mirror = project_dir / 'journals' / 'backtest_history.jsonl'
    _local_hist = project_dir / 'checkpoints' / 'backtest_history.jsonl'
    if _mirror.exists() and not args.no_checkpoints:
        try:
            _local_hist.parent.mkdir(parents=True, exist_ok=True)
            _n = _merge_jsonl(str(_mirror), str(_local_hist))
            total_copied += 1
            print(f"  ↳ backtest_history.jsonl из journals/ (копия бота): "
                  f"строк {_n}{_fmt_size(_local_hist)}")
        except OSError as exc:
            all_errors.append(('journals/backtest_history.jsonl', str(exc)))
    # Остальные лёгкие файлы состояния бот публикует в journals/ тем же вызовом
    # functions.publish_state_to_journals(): маркеры прогонов и деплоя.
    if not args.no_checkpoints:
        for _name in CHECKPOINT_LIGHT_FILES:
            if _name.endswith('.jsonl'):
                continue          # уже слит выше
            _src_pub = project_dir / 'journals' / _name
            _dst_ck = project_dir / 'checkpoints' / _name
            if not _src_pub.exists():
                continue
            try:
                if _dst_ck.exists() and _dst_ck.stat().st_mtime >= _src_pub.stat().st_mtime:
                    continue
                _dst_ck.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(_src_pub, _dst_ck)
                total_copied += 1
                print(f"  ↳ {_name} из journals/ (публикация бота){_fmt_size(_dst_ck)}")
            except OSError as exc:
                all_errors.append((f'journals/{_name}', str(exc)))
    print()

    elapsed = (datetime.now() - start_time).total_seconds()

    print("=" * 70)
    print("  ИТОГ")
    print("=" * 70)
    print(f"  ✓ Скопировано:     {total_copied}")
    print(f"  ✗ Ошибок:          {len(all_errors)}")
    print(f"  ⏭ Пропущено:       {total_skipped}")
    print(f"  ⏱ Время:           {elapsed:.2f} сек")
    if not args.no_checkpoints:
        print(_history_summary())
    print()
    print()

    if all_errors:
        print("  Ошибки:")
        for filename, error in all_errors:
            print(f"    - {filename}: {error}")
        print()

    if total_copied > 0:
        _hist = project_dir / 'checkpoints' / 'backtest_history.jsonl'
        _state_ok = _hist.exists() and _hist.stat().st_size > 0
        print("  ✅ Синхронизация завершена успешно!" if (not all_errors or _state_ok) else
              "  ⚠ Синхронизация завершена ЧАСТИЧНО: journals/ приехали, "
              "но checkpoints/ — нет (вкладка Backtest останется пустой).")
        if _state_ok and all_errors:
            print("     (checkpoints/ по сети недоступен — состояние взято из journals/)")
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
