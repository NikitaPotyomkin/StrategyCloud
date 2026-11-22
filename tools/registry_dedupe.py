"""Удаление повторяющихся ключей реестра — на ast, с самопроверкой.

Почему не текстовым парсером: запись реестра заканчивается строкой «),», но
так же заканчиваются вложенные структуры, поэтому эвристика «до первой ),»
рвёт файл. Здесь границы берутся из ast: начало записи — строка ключа, конец —
end_lineno значения. Для ключей внутри ENABLED_BATCH — вырезание ровно по
col_offset/end_col_offset, а не по строкам (в одной строке бывает 5 ключей).

Что делает:
  * в REGISTRY находит ключи, объявленные больше одного раза, и оставляет
    ПОСЛЕДНЕЕ вхождение. Именно оно сейчас и работает: Python схлопывает
    дубли в словаре, побеждает последний, — поэтому поведение не меняется;
  * в ENABLED_BATCH убирает повторные упоминания ключа, сохраняя последнее;
  * по умолчанию только печатает план, файл НЕ трогает;
  * с --write пишет файл, но только если новый текст проходит ast.parse,
    а набор ключей реестра и батча не изменился. Перед записью — резервная
    копия в journals/.

Запуск:
    python tools/registry_dedupe.py            # план, файл не меняется
    python tools/registry_dedupe.py --write    # применить
"""
import ast
import os
import sys
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'strategies', '_registry.py')
BACKUP_DIR = os.path.join(ROOT, 'journals')


def collect(tree):
    """Записи REGISTRY и элементы ENABLED_BATCH с границами из ast."""
    reg, batch = [], []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if not isinstance(tgt, ast.Name):
                    continue
                if tgt.id == 'REGISTRY' and isinstance(node.value, ast.Dict):
                    reg += _reg_items(node.value)
                elif tgt.id == 'ENABLED_BATCH' and isinstance(node.value, (ast.Tuple, ast.List)):
                    batch += _batch_items(node.value)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            fn = call.func
            if (isinstance(fn, ast.Attribute) and fn.attr == 'update'
                    and isinstance(fn.value, ast.Name) and fn.value.id == 'REGISTRY'
                    and call.args and isinstance(call.args[0], ast.Dict)):
                reg += _reg_items(call.args[0])
    return reg, batch


def _reg_items(dict_node):
    items = []
    for key, val in zip(dict_node.keys, dict_node.values):
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            items.append({
                'key': key.value,
                'start': min(key.lineno, val.lineno),
                'end': val.end_lineno,
                'node': val,
            })
    return items


def _batch_items(tuple_node):
    items = []
    for el in tuple_node.elts:
        if isinstance(el, ast.Constant) and isinstance(el.value, str):
            items.append({
                'key': el.value,
                'line': el.lineno,
                'col': el.col_offset,
                'end_col': el.end_col_offset,
            })
    return items


def spec_brief(node):
    """'label=..., grid=[...], min_len=...' из вызова dict(...)."""
    out = {}
    for kw in getattr(node, 'keywords', []):
        try:
            out[kw.arg] = ast.literal_eval(kw.value)
        except (ValueError, SyntaxError):
            out[kw.arg] = '<выражение>'
    parts = []
    for name in ('label', 'grid', 'min_len'):
        if name in out:
            parts.append(f"{name}={out[name]}")
    return ', '.join(parts) if parts else '<нет полей>'


def main():
    write = '--write' in sys.argv[1:]

    with open(SRC, 'r', encoding='utf-8', newline='') as fh:
        text = fh.read()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    reg, batch = collect(tree)

    print(f"REGISTRY: вхождений {len(reg)}, уникальных {len({i['key'] for i in reg})}")
    print(f"ENABLED_BATCH: вхождений {len(batch)}, уникальных {len({i['key'] for i in batch})}")

    before_reg = {i['key'] for i in reg}
    before_batch = {i['key'] for i in batch}

    # ── 1. Дубли в REGISTRY: удаляем все вхождения, кроме последнего ──
    groups = defaultdict(list)
    for item in reg:
        groups[item['key']].append(item)

    drop_lines = set()
    n_reg_removed = 0
    for key in sorted(groups):
        items = sorted(groups[key], key=lambda d: d['start'])
        if len(items) < 2:
            continue
        keep = items[-1]
        print(f"\n  {key}: оставляем строку {keep['start']} ({spec_brief(keep['node'])})")
        for item in items[:-1]:
            print(f"    удаляем строки {item['start']}-{item['end']} ({spec_brief(item['node'])})")
            drop_lines.update(range(item['start'], item['end'] + 1))
            n_reg_removed += 1

    # ── 2. Дубли в ENABLED_BATCH: вырезаем повторные упоминания ──
    b_groups = defaultdict(list)
    for item in batch:
        b_groups[item['key']].append(item)

    cuts = []
    for key in sorted(b_groups):
        items = sorted(b_groups[key], key=lambda d: (d['line'], d['col']))
        if len(items) < 2:
            continue
        print(f"\n  ENABLED_BATCH {key}: оставляем строку {items[-1]['line']}, "
              f"убираем повтор на строках {', '.join(str(i['line']) for i in items[:-1])}")
        cuts += items[:-1]

    by_line = defaultdict(list)
    for item in cuts:
        by_line[item['line'] - 1].append(item)

    for idx, items in by_line.items():
        line = lines[idx]
        if not line.isascii():
            raise SystemExit(f"[ОТКАЗ] строка {idx + 1} не ASCII — вырезание по колонкам "
                             f"небезопасно, правьте вручную")
        for item in sorted(items, key=lambda d: d['col'], reverse=True):
            # Перечитываем строку: вырезание идёт справа налево, но после
            # предыдущей правки текст в строке уже другой.
            line = lines[idx]
            start, end = item['col'], item['end_col']
            expect = "'" + item['key'] + "'"
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

    if not drop_lines and not cuts:
        print("\nДублей нет — файл не меняется.")
        return

    new_text = ''.join(ln for i, ln in enumerate(lines, start=1) if i not in drop_lines)

    # ── 3. Самопроверка: парсится, набор ключей не изменился ──
    try:
        new_tree = ast.parse(new_text)
    except SyntaxError as exc:
        raise SystemExit(f"[ОТКАЗ] новый текст не парсится: {exc}")

    new_reg, new_batch = collect(new_tree)
    new_reg_keys = {i['key'] for i in new_reg}
    new_batch_keys = {i['key'] for i in new_batch}

    problems = []
    if new_reg_keys != before_reg:
        problems.append(f"изменился набор ключей REGISTRY: "
                        f"пропали {sorted(before_reg - new_reg_keys)}, "
                        f"появились {sorted(new_reg_keys - before_reg)}")
    if new_batch_keys != before_batch:
        problems.append(f"изменился набор ключей ENABLED_BATCH: "
                        f"пропали {sorted(before_batch - new_batch_keys)}, "
                        f"появились {sorted(new_batch_keys - before_batch)}")
    if len(new_reg) != len(reg) - n_reg_removed:
        problems.append(f"REGISTRY: было вхождений {len(reg)}, удаляли {n_reg_removed}, "
                        f"стало {len(new_reg)}")
    if len(new_batch) != len(batch) - len(cuts):
        problems.append(f"ENABLED_BATCH: было вхождений {len(batch)}, вырезали {len(cuts)}, "
                        f"стало {len(new_batch)}")
    if problems:
        for msg in problems:
            print(f"[ОТКАЗ] {msg}")
        raise SystemExit(1)

    print(f"\nИтог: удаляем {len(drop_lines)} строк; "
          f"REGISTRY {len(reg)} -> {len(new_reg)} вхождений "
          f"({len(new_reg_keys)} уникальных), "
          f"ENABLED_BATCH {len(batch)} -> {len(new_batch)} вхождений")
    print("Проверка ast: новый текст парсится, наборы ключей совпадают.")

    if not write:
        print("\nDry-run: файл не изменён. Для применения: --write")
        return

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = os.path.join(BACKUP_DIR, f'_registry.py.bak-{stamp}')
    with open(backup, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)
    with open(SRC, 'w', encoding='utf-8', newline='') as fh:
        fh.write(new_text)

    print(f"\nЗаписано: {SRC}")
    print(f"Резервная копия: {backup}")
    print("Проверка: python tools/registry_audit.py — дублей должно стать 0.")


if __name__ == '__main__':
    main()
