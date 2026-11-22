"""Точечное удаление ключей реестра: REGISTRY + ENABLED_BATCH.

Обобщение clone_prune: ключи берутся из командной строки, а не из константы.
Нужно для случаев, когда ключ не клон и не дубль, а просто не нужен (модуль
делает не то, что обещает имя, или дублирует уже закрытую логику).

Границы записей берутся из ast (начало — строка ключа, конец — end_lineno
значения), ключи в кортеже вырезаются по col_offset/end_col_offset.

Перед удалением проверяются квоты и активации: удалять ключ, по которому есть
открытые квоты, нельзя — движок останется без записи реестра и осиротит сделки.
Ищем по двум именам сразу: по ключу реестра и по label, потому что в журналах
и в steering_quotas.json ключ встречается в обоих видах.

Защита:
  * по умолчанию только печатает план, файл не меняется;
  * с --write пишет файл, но лишь если новый текст парсится, наборы ключей
    изменились РОВНО на список удаляемых и дублей не осталось;
  * перед записью — резервная копия в journals/.

Запуск:
    python tools/registry_remove.py sess_hour            # план
    python tools/registry_remove.py sess_hour --write    # применить
"""
import ast
import json
import os
import sys
from collections import Counter
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from registry_dedupe import collect  # noqa: E402

SRC = os.path.join(ROOT, 'strategies', '_registry.py')
JOURNALS = os.path.join(ROOT, 'journals')


def usage_check(names):
    """Сколько квот и активаций у ключей.

    names — {ключ реестра: [ключ, label]}. В журналах ключ живёт и как ключ
    реестра, и как короткая метка, поэтому ищем по обоим именам.

    Квота — запись вида <символ>_<имя> в steering_quotas.json. Активация — строка
    в strategy_registry.csv, где имя встречается. Ненулевая активация значит,
    что ключ участвует в живом плане, и удалять его из реестра нельзя.
    """
    quotas = {k: 0 for k in names}
    path = os.path.join(JOURNALS, 'steering_quotas.json')
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        for quota_key in data:
            for key, aliases in names.items():
                if any(quota_key.endswith('_' + a) for a in aliases):
                    quotas[key] += 1
                    break

    active = {k: 0 for k in names}
    path = os.path.join(JOURNALS, 'strategy_registry.csv')
    if os.path.isfile(path):
        with open(path, encoding='utf-8', errors='replace') as fh:
            rows = fh.read().splitlines()[1:]  # без шапки
        for key, aliases in names.items():
            active[key] = sum(1 for row in rows if any(a in row for a in aliases))
    return quotas, active


def main():
    write = '--write' in sys.argv[1:]
    keys = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not keys:
        raise SystemExit("укажите ключи: python tools/registry_remove.py <key> "
                         "[<key> ...] [--write]")

    with open(SRC, 'r', encoding='utf-8', newline='') as fh:
        text = fh.read()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    reg, batch = collect(tree)

    before_reg = {i['key'] for i in reg}
    before_batch = {i['key'] for i in batch}
    print(f"REGISTRY: вхождений {len(reg)}, уникальных {len(before_reg)}")
    print(f"ENABLED_BATCH: вхождений {len(batch)}, уникальных {len(before_batch)}")

    present = [k for k in keys if k in before_reg or k in before_batch]
    missing = [k for k in keys if k not in before_reg and k not in before_batch]
    if missing:
        print(f"нет в реестре (пропускаю): {', '.join(missing)}")
    if not present:
        print("\nУдалять нечего — файл не меняется.")
        return

    by_key = {}
    for item in reg:
        by_key.setdefault(item['key'], item)

    # ── 0. Квоты и активации ──
    names = {}
    for key in present:
        aliases = [key]
        item = by_key.get(key)
        if item is not None:
            for kw in getattr(item['node'], 'keywords', []):
                if kw.arg != 'label':
                    continue
                try:
                    label = ast.literal_eval(kw.value)
                except ValueError:
                    label = None
                if label and label not in aliases:
                    aliases.append(label)
        names[key] = aliases

    quotas, active = usage_check(names)
    print("\nИспользование:")
    blocked = []
    for key in present:
        shown = ' / '.join(names[key])
        print(f"  {key} ({shown}): квот {quotas[key]}, активаций {active[key]}")
        if active[key] > 0:
            blocked.append(key)
    if blocked:
        raise SystemExit(f"[ОТКАЗ] у ключей есть активации в плане: "
                         f"{', '.join(blocked)} — сначала снимите их в движке")

    # ── 1. Удаление записей REGISTRY ──
    drop_lines = set()
    for key in present:
        item = by_key.get(key)
        if item is None:
            print(f"\n  {key}: записи REGISTRY нет — только батч")
            continue
        print(f"\n  удаляем {key}: строки {item['start']}-{item['end']}")
        drop_lines.update(range(item['start'], item['end'] + 1))

    # ── 2. Вырезание ключей из ENABLED_BATCH ──
    ops = {}
    cut_count = 0
    for item in batch:
        if item['key'] not in present:
            continue
        ops.setdefault(item['line'] - 1, []).append(
            {'key': item['key'], 'start': item['col'], 'end': item['end_col']})
        cut_count += 1
    print(f"\n  из ENABLED_BATCH вырезаем {cut_count} упоминаний")

    # ── 3. Применение правок: справа налево, чтобы offsets не съезжали ──
    for idx, line_ops in ops.items():
        for op in sorted(line_ops, key=lambda o: o['start'], reverse=True):
            line = lines[idx]
            if not line.isascii():
                raise SystemExit(f"[ОТКАЗ] строка {idx + 1} не ASCII — вырезание по "
                                 f"колонкам небезопасно, правьте вручную")
            start, end = op['start'], op['end']
            expect = "'" + op['key'] + "'"
            if line[start:end] != expect:
                raise SystemExit(f"[ОТКАЗ] строка {idx + 1}: ожидался {expect!r}, "
                                 f"найдено {line[start:end]!r}")
            if line[end:end + 1] == ',':
                end += 1
                if line[end:end + 1] == ' ':
                    end += 1
            lines[idx] = line[:start] + line[end:]
        if lines[idx].strip() == '':
            drop_lines.add(idx + 1)

    new_text = ''.join(ln for i, ln in enumerate(lines, start=1) if i not in drop_lines)

    # ── 4. Самопроверка ──
    try:
        new_tree = ast.parse(new_text)
    except SyntaxError as exc:
        raise SystemExit(f"[ОТКАЗ] новый текст не парсится: {exc}")

    new_reg, new_batch = collect(new_tree)
    new_reg_keys = {i['key'] for i in new_reg}
    new_batch_keys = {i['key'] for i in new_batch}
    expect_reg = before_reg - set(present)
    expect_batch = before_batch - set(present)

    problems = []
    if new_reg_keys != expect_reg:
        problems.append(f"REGISTRY: пропали {sorted(expect_reg - new_reg_keys)}, "
                        f"лишние {sorted(new_reg_keys - expect_reg)}")
    if new_batch_keys != expect_batch:
        problems.append(f"ENABLED_BATCH: пропали {sorted(expect_batch - new_batch_keys)}, "
                        f"лишние {sorted(new_batch_keys - expect_batch)}")
    dupes = [k for k, n in Counter(i['key'] for i in new_reg).items() if n > 1]
    if dupes:
        problems.append(f"в REGISTRY остались дубли: {sorted(dupes)}")
    dupes_b = [k for k, n in Counter(i['key'] for i in new_batch).items() if n > 1]
    if dupes_b:
        problems.append(f"в ENABLED_BATCH остались дубли: {sorted(dupes_b)}")

    if problems:
        for msg in problems:
            print(f"[ОТКАЗ] {msg}")
        raise SystemExit(1)

    print(f"\nИтог: удаляем {len(present)} ключей, строк {len(drop_lines)}; "
          f"REGISTRY {len(before_reg)} -> {len(new_reg_keys)}, "
          f"ENABLED_BATCH {len(before_batch)} -> {len(new_batch_keys)}")
    print("Проверка ast: текст парсится, наборы ключей и дубли совпадают.")

    if not write:
        print("\nDry-run: файл не изменён. Для применения: --write")
        return

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = os.path.join(JOURNALS, f'_registry.py.bak-remove-{stamp}')
    with open(backup, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)
    with open(SRC, 'w', encoding='utf-8', newline='') as fh:
        fh.write(new_text)

    print(f"\nЗаписано: {SRC}")
    print(f"Резервная копия: {backup}")
    print("Проверка: python tools/registry_audit.py — ключей должно стать "
          f"{len(new_reg_keys)}.")


if __name__ == '__main__':
    main()
