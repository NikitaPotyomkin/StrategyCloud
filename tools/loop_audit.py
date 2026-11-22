"""Аудит модели бэктеста у каждого ключа реестра (только чтение).

Зачем: реестр держит 208 ключей, но считаются они двумя-тремя разными
способами. Пока это не разложено по полочкам, любое «починим стратегии»
превращается в правку наугад.

Классификация backtest модуля (флаги не взаимоисключающие):
  core        — вызывает strategies._bt_core.run_backtest: вход по open[i+1],
                спред с двух сторон, без обрыва по времени, деньги через
                trade_profit (÷ tick_size). Это эталон.
  timeout50   — своя петля с обрывом: range(i+1, min(i+50, ...)). Сделка, не
                закрывшаяся за 49 баров, выпадает из выборки целиком.
  unscaled    — P&L как diff * sim_lot * tick_value и ни одного деления на
                tick_size: деньги занижены в 1/tick_size раз (EURUSD 1e-5).
  position    — своя петля с управлением позицией и вызовом check_exit.
  close_entry — вход по close[i] сигнального бара.
  other       — своя петля, ни один признак не сработал (разбирать вручную).
  missing     — файла модуля нет.
  syntax_error / no_backtest — файл не парсится или в нём нет backtest.

Запуск:
    python tools/loop_audit.py
    python tools/loop_audit.py --family mr_
"""
import argparse
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

STRATEGIES = os.path.join(ROOT, 'strategies')

# Регулярки по тексту, а не по ast: формы записи разные (i+50 / i + 50),
# а нам нужен факт, а не структура.
RE_TIMEOUT = re.compile(r'min\(\s*i\s*\+\s*50\s*,')
RE_UNSCALED = re.compile(r'\*\s*sim_lot\s*\*\s*tick_value')
RE_TICKDIV = re.compile(r'/\s*tick_size')


def classify(path):
    """(флаги, примечание) для одного файла модуля."""
    with open(path, 'r', encoding='utf-8') as fh:
        text = fh.read()
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return ['syntax_error'], f'не парсится: {exc}'

    func = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'backtest':
            func = node
    if func is None:
        return ['no_backtest'], ''

    calls = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            calls.add(node.func.id)

    if 'run_backtest' in calls:
        return ['core'], ''
    if 'run_backtest_legacy' in calls:
        # Шаг C: арифметика исправлена (спред, ÷tick_size), но модель входа
        # прежняя — по эталону это ещё не core.
        return ['core_legacy'], ''

    flags = []
    if RE_TIMEOUT.search(text):
        flags.append('timeout50')
    if RE_UNSCALED.search(text) and not RE_TICKDIV.search(text):
        flags.append('unscaled')
    if 'check_exit' in calls:
        flags.append('position')
    if "df['close'].iloc[i]" in text:
        flags.append('close_entry')
    if not flags:
        flags.append('other')
    return flags, ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family', default='', help='фильтр по префиксу модуля')
    args = parser.parse_args()

    from strategies import _registry as reg

    rows = []
    for key in sorted(reg.REGISTRY):
        record = reg.REGISTRY[key]
        module = str(record.get('module', ''))
        if args.family and not module.startswith(args.family):
            continue
        path = os.path.join(STRATEGIES, module + '.py')
        if not os.path.isfile(path):
            rows.append((key, module, ['missing'], ''))
            continue
        flags, note = classify(path)
        rows.append((key, module, flags, note))

    if not rows:
        raise SystemExit('под фильтр ничего не попало')

    width = max(len(key) for key, _, _, _ in rows)
    for key, module, flags, note in rows:
        print(f"{key:<{width}}  {module:<36} {','.join(flags):<30} {note}")

    counts = {}
    for _, _, flags, _ in rows:
        sig = ','.join(flags)
        counts[sig] = counts.get(sig, 0) + 1

    print(f"\nКлючей: {len(rows)}")
    for sig, n in sorted(counts.items(), key=lambda item: -item[1]):
        print(f"  {n:>4}  {sig}")

    off_core = [row for row in rows if 'core' not in row[2]]
    print(f"\nНе на эталонном движке: {len(off_core)} из {len(rows)}")
    if off_core:
        print("Шаг C (сравнимые деньги): python tools/loop_to_core.py --model legacy")
        print("Шаг B (эталонный движок): python tools/loop_to_core.py --model core")


if __name__ == '__main__':
    main()
