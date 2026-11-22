"""Аудит реестра стратегий — ТОЛЬКО ЧТЕНИЕ, ничего не пишет и не меняет.

Python молча схлопывает повторяющиеся ключи в словаре (побеждает последний),
поэтому дубли ищутся не по REGISTRY, а по исходнику через ast — с номерами
строк, чтобы видно было, какое вхождение «проиграло».

Проверяет:
  * повторы ключей в литерале REGISTRY (в т.ч. в REGISTRY.update({...}));
  * повторы ключей в ENABLED_BATCH (это лишние бэктесты, не искажение);
  * ключи, которые есть в реестре, но не включены в батч (и наоборот);
  * коллизии label — они затирают друг друга в enabled_families/family_fp
    и ломают инкрементальный пересчёт;
  * клоны: несколько ключей реестра на один и тот же модуль;
  * слои: существует ли файл модуля и есть ли в нём объявленная calc-функция.

Запуск:
    python tools/registry_audit.py
"""
import ast
import importlib
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'strategies', '_registry.py')
STRAT = os.path.join(ROOT, 'strategies')

sys.path.insert(0, ROOT)


def _str_keys(dict_node):
    """[(ключ, строка)] для строковых ключей словарного литерала."""
    out = []
    for k in dict_node.keys:
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            out.append((k.value, k.lineno))
    return out


def scan_source():
    """Записи REGISTRY и ENABLED_BATCH как в файле, с номерами строк."""
    with open(SRC, encoding='utf-8') as fh:
        tree = ast.parse(fh.read())

    reg, batch = [], []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if not isinstance(tgt, ast.Name):
                    continue
                if tgt.id == 'REGISTRY' and isinstance(node.value, ast.Dict):
                    reg += _str_keys(node.value)
                elif tgt.id == 'ENABLED_BATCH' and isinstance(node.value, (ast.Tuple, ast.List)):
                    for el in node.value.elts:
                        if isinstance(el, ast.Constant) and isinstance(el.value, str):
                            batch.append((el.value, el.lineno))
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            fn = call.func
            if (isinstance(fn, ast.Attribute) and fn.attr == 'update'
                    and isinstance(fn.value, ast.Name) and fn.value.id == 'REGISTRY'
                    and call.args and isinstance(call.args[0], ast.Dict)):
                reg += _str_keys(call.args[0])
    return reg, batch


def report_dupes(entries, what):
    cnt = Counter(k for k, _ in entries)
    dupes = [k for k, v in cnt.items() if v > 1]
    print(f"\n[{what}] вхождений {len(entries)}, уникальных {len(cnt)}, дублей {len(dupes)}")
    for key in dupes:
        lines = ', '.join(str(ln) for kk, ln in entries if kk == key)
        print(f"  {key}: строки {lines}")
    return dupes


def main():
    from strategies import _registry as r

    reg_src, batch_src = scan_source()

    print(f"REGISTRY как объект: {len(r.REGISTRY)} ключей")
    report_dupes(reg_src, 'REGISTRY в исходнике')
    report_dupes(batch_src, 'ENABLED_BATCH')

    reg_keys = set(r.REGISTRY)
    batch_unique = {k for k, _ in batch_src}
    enabled_unique = set(r.enabled_keys())
    print(f"\nбатч уникальных: {len(batch_unique)}; реально включено: {len(enabled_unique)}")

    only_reg = reg_keys - batch_unique
    if only_reg:
        print(f"\n[есть в REGISTRY, нет в батче] {len(only_reg)}:")
        for key in sorted(only_reg):
            print(f"  {key}")
    only_batch = batch_unique - reg_keys
    if only_batch:
        print(f"\n[есть в батче, нет в REGISTRY] {len(only_batch)}:")
        for key in sorted(only_batch):
            print(f"  {key}")

    labels, modules = defaultdict(list), defaultdict(list)
    for key, spec in r.REGISTRY.items():
        labels[spec.get('label')].append(key)
        modules[spec.get('module') or key].append(key)

    print("\n[коллизии label]")
    lbl_bad = {lbl: ks for lbl, ks in labels.items() if len(ks) > 1}
    if not lbl_bad:
        print("  нет")
    for lbl, keys in sorted(lbl_bad.items(), key=lambda kv: str(kv[0])):
        print(f"  {lbl}: {', '.join(sorted(keys))}")

    clones = {m: ks for m, ks in modules.items() if len(ks) > 1}
    print(f"\n[клоны: несколько ключей на один модуль] групп {len(clones)}, "
          f"лишних ключей {sum(len(v) - 1 for v in clones.values())}")
    for mod, keys in sorted(clones.items()):
        print(f"  {mod}: {', '.join(sorted(keys))}")

    print("\n[слои: файл модуля и calc-функция]")
    problems = []
    for key, spec in sorted(r.REGISTRY.items()):
        mod = spec.get('module') or key
        calc = spec.get('calc') or ''
        path = os.path.join(STRAT, mod + '.py')
        if not os.path.exists(path):
            problems.append(f"{key}: нет файла strategies/{mod}.py")
            continue
        try:
            mod_obj = importlib.import_module('strategies.' + mod)
        except Exception as exc:  # noqa: BLE001 — отчёт, а не падение
            problems.append(f"{key}: импорт strategies/{mod}.py упал: {exc!r}")
            continue
        if not hasattr(mod_obj, calc):
            problems.append(f"{key}: в strategies/{mod}.py нет функции {calc}")
    if not problems:
        print("  проблем нет")
    for line in problems:
        print(f"  {line}")


if __name__ == '__main__':
    main()
