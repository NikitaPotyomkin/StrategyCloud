"""P3: выравнивание live-входов с бэктестом для 44 ключей.

Почему: в backtest() эти модули передают _bt_core.state_entry — вход разрешён при
"curr == 1 и prev != 1", то есть разворот -1 -> +1 тоже вход. Live собирается из
REGISTRY, где у них указан модульный check_entry (строгий, prev == 0), и разворот
пропускался. Здесь entry/exit таких записей переводятся на state_entry/state_exit.
Ничего другого не меняется: value-cross стратегии (84 ключа) не трогаем.

Список ключей получен из tools/entry_semantics_audit.py — это те, у кого
backtest() использует state_entry И модульный check_entry строгий.

Запуск:
    python tools/live_parity_fix.py            # план
    python tools/live_parity_fix.py --write    # применить
"""
import ast
import os
import sys
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from registry_dedupe import collect  # noqa: E402

SRC = os.path.join(ROOT, 'strategies', '_registry.py')
BACKUP_DIR = os.path.join(ROOT, 'journals')

STATE_KEYS = (
    'anom_huge_vol', 'anom_liq_hole', 'anom_long_wick', 'anom_spread_bo',
    'anom_stop_run',
    'cyc_bandpass', 'cyc_fft', 'cyc_hilbert', 'cyc_spec_ent', 'cyc_wavelet',
    'port_alpha', 'port_kill', 'port_live_bt', 'port_min_trades', 'port_sharpe',
    'reg_bayesian', 'reg_elasticnet', 'reg_lasso', 'reg_poly', 'reg_quantile',
    'reg_ransac', 'reg_ridge', 'reg_theilsen',
    'regime_bocpd', 'regime_cusum_ret', 'regime_duration', 'regime_markov_q',
    'regime_stress',
    'sess_asian', 'sess_hour', 'sess_ldn',
    'stat_acf', 'stat_adf_regime', 'stat_ks', 'stat_ljung', 'stat_vr',
    'struct_bos', 'struct_eqhighs', 'struct_fvg', 'struct_liq_swp', 'struct_rex',
    'volprof_cvd_div', 'volprof_poc_break', 'volreg_volofvol',
)

RENAME = {'entry': ('check_entry', 'state_entry'),
          'exit': ('check_exit', 'state_exit')}


def main():
    write = '--write' in sys.argv[1:]

    with open(SRC, 'r', encoding='utf-8', newline='') as fh:
        text = fh.read()
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    reg, _ = collect(tree)
    by_key = {}
    for item in reg:
        by_key.setdefault(item['key'], item)

    from strategies import _registry as r  # noqa: E402 — пакет уже на диске

    ops = defaultdict(list)
    patched, skipped = [], []
    for key in STATE_KEYS:
        item = by_key.get(key)
        if item is None:
            skipped.append(f"{key}: нет в реестре")
            continue
        mod = r._module(r.REGISTRY[key]['module'])
        if not hasattr(mod, 'state_entry') or not hasattr(mod, 'state_exit'):
            skipped.append(f"{key}: модуль не экспортирует state_entry/state_exit")
            continue
        kws = {kw.arg: kw for kw in getattr(item['node'], 'keywords', [])}
        changed = False
        for field, (old, new) in RENAME.items():
            kw = kws.get(field)
            if kw is None or not isinstance(kw.value, ast.Constant):
                skipped.append(f"{key}: поле {field} не строка")
                continue
            if kw.value.value == new:
                continue
            if kw.value.value != old:
                skipped.append(f"{key}.{field} = {kw.value.value!r} — не трогаю")
                continue
            node = kw.value
            if node.lineno != node.end_lineno:
                skipped.append(f"{key}.{field} в несколько строк")
                continue
            ops[node.lineno - 1].append({'start': node.col_offset,
                                         'end': node.end_col_offset,
                                         'text': repr(new)})
            changed = True
        if changed:
            patched.append(key)

    if skipped:
        print("пропущено:")
        for line in skipped:
            print(f"  {line}")
    if not ops:
        print("\nМенять нечего — файл не изменён.")
        return

    print(f"\nпереводим entry/exit на state-семантику: {len(patched)} ключей")
    print("  " + ', '.join(patched))

    for idx, line_ops in ops.items():
        if not lines[idx].isascii():
            raise SystemExit(f"[ОТКАЗ] строка {idx + 1} не ASCII")
        for op in sorted(line_ops, key=lambda o: o['start'], reverse=True):
            line = lines[idx]
            lines[idx] = line[:op['start']] + op['text'] + line[op['end']:]
    new_text = ''.join(lines)

    try:
        new_tree = ast.parse(new_text)
    except SyntaxError as exc:
        raise SystemExit(f"[ОТКАЗ] новый текст не парсится: {exc}")
    new_reg, _ = collect(new_tree)
    if len(new_reg) != len(reg) or {i['key'] for i in new_reg} != {i['key'] for i in reg}:
        raise SystemExit("[ОТКАЗ] изменился набор записей REGISTRY")

    new_by_key = {i['key']: i for i in new_reg}
    problems = []
    for key in patched:
        kws = {kw.arg: kw for kw in getattr(new_by_key[key]['node'], 'keywords', [])}
        for field, (_, new) in RENAME.items():
            got = kws[field].value.value if field in kws else None
            if got != new:
                problems.append(f"{key}.{field} = {got!r}, ожидалось {new!r}")
    if problems:
        for msg in problems:
            print(f"[ОТКАЗ] {msg}")
        raise SystemExit(1)

    print("Проверка ast: парсится, набор записей тот же, поля переписаны.")
    if not write:
        print("\nDry-run: файл не изменён. Для применения: --write")
        return

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = os.path.join(BACKUP_DIR, f'_registry.py.bak-live-{stamp}')
    with open(backup, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)
    with open(SRC, 'w', encoding='utf-8', newline='') as fh:
        fh.write(new_text)
    print(f"\nЗаписано: {SRC}\nРезервная копия: {backup}")


if __name__ == '__main__':
    main()
