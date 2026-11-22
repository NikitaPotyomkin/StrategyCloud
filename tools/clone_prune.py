"""Чистка клонов реестра (P1): один ключ на модуль.

Клон — несколько ключей реестра на ОДИН модуль. Копии получают отдельные квоты
(max_per_type считается по ключу), отдельный вес в штурвале и лишние бэктесты.
Здесь лишние ключи удаляются из REGISTRY и ENABLED_BATCH, а у трёх оставляемых
записей правится сетка параметров, чтобы не потерять значения из удаляемых.

Границы записей берутся из ast (начало — строка ключа, конец — end_lineno
значения), ключи в кортеже вырезаются по col_offset/end_col_offset.

Защита:
  * по умолчанию только печатает план, файл не меняется;
  * с --write пишет файл, но лишь если новый текст парсится, наборы ключей
    изменились РОВНО на список удаляемых, дублей не осталось, а новые значения
    grid/min_len совпадают с заявленными;
  * перед записью — резервная копия в journals/.

Запуск:
    python tools/clone_prune.py            # план
    python tools/clone_prune.py --write    # применить
"""
import ast
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from registry_dedupe import collect  # noqa: E402

SRC = os.path.join(ROOT, 'strategies', '_registry.py')
BACKUP_DIR = os.path.join(ROOT, 'journals')

# Удаляемые ключи-клоны. В группе остаётся тот, что назван в комментарии.
REMOVE = (
    # chan_donchian_pct_squeeze остаётся (grid [20,34,55])
    'chan_dsc_sq',
    # chan_regression_band_z остаётся (сетки идентичны)
    'chan_regz',
    # mom_efficiency / mom_pullback_ratio / mom_roc_of_roc остаются (сетки шире)
    'mom_eff', 'mom_pull', 'mom_ror',
    # osc_* — остаются версии без суффикса _alt (сетки шире)
    'osc_fisher_alt', 'osc_pgo_alt', 'osc_ravi_alt', 'osc_tii_alt',
    # pattern_flag_bull / pattern_triangle_sym остаются
    'pat_flag', 'pat_tri',
    # статистика: остаются ключи, совпадающие с именем модуля
    'stat_acf2',        # остаётся stat_acf (сетки идентичны)
    'stat_adf',         # остаётся stat_adf_regime
    'stat_hl',          # остаётся stat_half_life
    'stat_ks2',         # остаётся stat_ks (min_len 200 строже, чем 150)
    'stat_lb',          # остаётся stat_ljung (grid расширяется ниже)
    'stat_lz',          # остаётся stat_lz_complexity
    # структура: остаётся struct_liq_swp, у struct_swing_bos — три ключа
    'struct_lsq',
    'struct_swing',
    'swing_bos',
    # профиль объёма: остаются volprof_cvd_div, volprof_poc_break, volprof_vol_imbalance
    'volprof_cvd2', 'volprof_poc', 'volprof_imb',
    # волатильность: остаются версии без суффикса _alt
    'volreg_nr7_alt', 'volreg_range_exp_alt', 'volreg_vol_of_vol2', 'volreg_yz_alt',
)

# Правки оставляемых записей, чтобы не потерять параметры удаляемых клонов.
PATCH = {
    # было [50,100], у stat_lb был 20
    'stat_ljung': {'grid': [20, 50, 100]},
    # было [5,10] min_len 40; у swing_bos был 20, min_len 40 слишком мал
    'struct_bos': {'grid': [5, 10, 20], 'min_len': 120},
    # было [1,5,20]; 1 — вырожденное окно, у volprof_poc был 10
    'volprof_poc_break': {'grid': [5, 10, 20]},
}


def _fmt(value):
    """Значение поля в стиле реестра: [5, 10, 20] или 120."""
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(str(v) for v in value) + ']'
    return str(value)


def main():
    write = '--write' in sys.argv[1:]

    with open(SRC, 'r', encoding='utf-8', newline='') as fh:
        text = fh.read()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    reg, batch = collect(tree)

    before_reg = {i['key'] for i in reg}
    before_batch = {i['key'] for i in batch}
    print(f"REGISTRY: вхождений {len(reg)}, уникальных {len(before_reg)}")
    print(f"ENABLED_BATCH: вхождений {len(batch)}, уникальных {len(before_batch)}")

    present = [k for k in REMOVE if k in before_reg]
    missing = [k for k in REMOVE if k not in before_reg]
    if missing:
        print(f"уже отсутствуют (пропускаю): {', '.join(missing)}")
    if not present:
        print("\nУдалять нечего — файл не меняется.")
        return

    # ── 1. Удаление записей REGISTRY ──
    drop_lines = set()
    by_key = {}
    for item in reg:
        by_key.setdefault(item['key'], item)
    for key in present:
        item = by_key[key]
        print(f"\n  удаляем {key}: строки {item['start']}-{item['end']}")
        drop_lines.update(range(item['start'], item['end'] + 1))

    # ── 2. Вырезание ключей из ENABLED_BATCH ──
    ops = defaultdict(list)
    cut_count = 0
    for item in batch:
        if item['key'] not in present:
            continue
        ops[item['line'] - 1].append({'kind': 'cut', 'key': item['key'],
                                      'start': item['col'], 'end': item['end_col']})
        cut_count += 1
    print(f"\n  из ENABLED_BATCH вырезаем {cut_count} упоминаний")

    # ── 3. Правка полей оставляемых записей ──
    for key, fields in PATCH.items():
        item = by_key.get(key)
        if item is None:
            print(f"  ВНИМАНИЕ: {key} нет в реестре — правку {fields} пропускаю")
            continue
        kws = {kw.arg: kw for kw in getattr(item['node'], 'keywords', [])}
        for name, value in fields.items():
            kw = kws.get(name)
            if kw is None:
                raise SystemExit(f"[ОТКАЗ] у {key} нет поля {name}")
            node = kw.value
            if node.lineno != node.end_lineno:
                raise SystemExit(f"[ОТКАЗ] {key}.{name} записано в несколько строк — "
                                 f"правьте вручную")
            print(f"  {key}: {name} -> {_fmt(value)}")
            ops[node.lineno - 1].append({'kind': 'patch', 'text': _fmt(value),
                                         'start': node.col_offset, 'end': node.end_col_offset})

    # ── 4. Применение правок: справа налево, чтобы offsets не съезжали ──
    for idx, line_ops in ops.items():
        for op in sorted(line_ops, key=lambda o: o['start'], reverse=True):
            line = lines[idx]
            if not line.isascii():
                raise SystemExit(f"[ОТКАЗ] строка {idx + 1} не ASCII — вырезание по "
                                 f"колонкам небезопасно, правьте вручную")
            start, end = op['start'], op['end']
            if op['kind'] == 'cut':
                expect = "'" + op['key'] + "'"
                if line[start:end] != expect:
                    raise SystemExit(f"[ОТКАЗ] строка {idx + 1}: ожидался {expect!r}, "
                                     f"найдено {line[start:end]!r}")
                if line[end:end + 1] == ',':
                    end += 1
                    if line[end:end + 1] == ' ':
                        end += 1
                lines[idx] = line[:start] + line[end:]
            else:
                lines[idx] = line[:start] + op['text'] + line[end:]
        if lines[idx].strip() == '':
            drop_lines.add(idx + 1)

    new_text = ''.join(ln for i, ln in enumerate(lines, start=1) if i not in drop_lines)

    # ── 5. Самопроверка ──
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

    new_by_key = {i['key']: i for i in new_reg}
    for key, fields in PATCH.items():
        item = new_by_key.get(key)
        if item is None:
            continue
        kws = {kw.arg: kw for kw in getattr(item['node'], 'keywords', [])}
        for name, value in fields.items():
            try:
                got = ast.literal_eval(kws[name].value)
            except (KeyError, ValueError):
                got = '<ошибка чтения>'
            if got != value:
                problems.append(f"{key}.{name}: ожидалось {value}, получено {got}")

    if problems:
        for msg in problems:
            print(f"[ОТКАЗ] {msg}")
        raise SystemExit(1)

    print(f"\nИтог: удаляем {len(present)} ключей, строк {len(drop_lines)}; "
          f"REGISTRY {len(before_reg)} -> {len(new_reg_keys)}, "
          f"ENABLED_BATCH {len(before_batch)} -> {len(new_batch_keys)}")
    print("Проверка ast: текст парсится, наборы ключей, дубли и правки совпадают.")

    if not write:
        print("\nDry-run: файл не изменён. Для применения: --write")
        return

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = os.path.join(BACKUP_DIR, f'_registry.py.bak-clones-{stamp}')
    with open(backup, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)
    with open(SRC, 'w', encoding='utf-8', newline='') as fh:
        fh.write(new_text)

    print(f"\nЗаписано: {SRC}")
    print(f"Резервная копия: {backup}")
    print("Проверка: python tools/registry_audit.py — клонов должно стать 0.")


if __name__ == '__main__':
    main()
