"""Перевод собственных петель бэктеста на общий движок strategies/_bt_core.

Поколение B (166 файлов) держит свою петлю: вход по close[i] сигнального бара,
спред не вычитается, незакрытая за 49 баров сделка молча выбрасывается,
P&L = diff * lot * tick_value без деления на tick_size. Поколение A и
run_backtest считают иначе — поэтому ranking сравнивает несравнимое.

Инструмент заменяет ТОЛЬКО функцию backtest: оставляет её сигнатуру, находит в
первой строке вызов calc_* и подставляет делегирование в run_backtest с теми же
calc/check_entry/check_exit. Логика расчёта сигнала не трогается.

Что НЕ переводится (печатается как «пропуск» и требует ручного разбора):
  * calc_* вызывается не с двумя аргументами или с выражением, отличным от
    param_key / int(param_key);
  * в файле нет функции backtest на уровне модуля;
  * в файле нет check_entry/check_exit (реестр может звать state_entry).

Защита: по умолчанию dry-run, файл не меняется; с --write каждый файл после
правки обязан распарситься, содержать ровно один Return в backtest и вызов
run_backtest. Файлы под git, поэтому откат — git checkout -- strategies/.

Запуск:
    python tools/loop_to_core.py --family mom_            # план
    python tools/loop_to_core.py --family mom_ --write    # применить
    python tools/loop_to_core.py --key mom_accel_z --write
"""
import argparse
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

STRATEGIES = os.path.join(ROOT, 'strategies')
IMPORT_LINE = 'from strategies._bt_core import run_backtest\n'

BODY = '''    """Симуляция сделок через общий движок strategies/_bt_core.run_backtest.

    Прежняя собственная петля входила по close сигнального бара (цена уже
    известна в момент входа), не вычитала спред, выбрасывала сделки, не
    закрывшиеся за 49 баров, и считала P&L как diff * lot * tick_value без
    деления на tick_size. Всё это давало несравнимые с остальным реестром
    числа — см. tools/loop_model_pilot.py.
    """
    return run_backtest(df, {calc}, check_entry, check_exit,
                        {param}, sl_points, tp_points, point,
                        tick_value, tick_size, sim_lot, spread_points)
'''


def _param_expr(call):
    """Выражение для param_key в вызове calc_* — либо None, если нестандартное."""
    if len(call.args) != 2:
        return None
    arg = call.args[1]
    if isinstance(arg, ast.Name) and arg.id == 'param_key':
        return 'param_key'
    # int(param_key) / float(param_key)
    if (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name)
            and arg.func.id in ('int', 'float')
            and len(arg.args) == 1
            and isinstance(arg.args[0], ast.Name)
            and arg.args[0].id == 'param_key'):
        return f'{arg.func.id}(param_key)'
    return None


def plan_file(path):
    """(план, причина_отказа). План — dict с строками и текстом замены."""
    with open(path, 'r', encoding='utf-8', newline='') as fh:
        text = fh.read()
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return None, f"не парсится: {exc}"

    func = None
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
            if node.name == 'backtest':
                func = node
    if func is None:
        return None, "нет def backtest на уровне модуля"
    for required in ('check_entry', 'check_exit'):
        if required not in names:
            return None, f"нет {required} (реестр может звать state_*)"

    calc_call = None
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id.startswith('calc_'):
            calc_call = node
            break
    if calc_call is None:
        return None, "в backtest нет вызова calc_*"

    param = _param_expr(calc_call)
    if param is None:
        try:
            shown = ast.unparse(calc_call.args[1]) if len(calc_call.args) > 1 else '<нет>'
        except Exception:                     # noqa: BLE001 — только для сообщения
            shown = '?'
        return None, (f"calc_* вызывается нестандартно: "
                      f"аргументов {len(calc_call.args)}, param={shown}")

    # Проверяем именно ВЫЗОВ, а не упоминание: в check_entry почти каждого файла
    # есть комментарий «... for engine run_backtest», и подстрочный поиск по
    # тексту давал ложный пропуск «уже использует run_backtest».
    if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
           and n.func.id == 'run_backtest' for n in ast.walk(tree)):
        return None, "уже использует run_backtest"

    lines = text.splitlines(keepends=True)
    head = ''.join(lines[:func.lineno - 1])
    if 'from strategies._bt_core import run_backtest' not in head:
        head += IMPORT_LINE
    signature = lines[func.lineno - 1]
    if not signature.rstrip().endswith(':'):
        return None, "сигнатура backtest записана в несколько строк"

    body = BODY.format(calc=calc_call.func.id, param=param)
    new_text = head + signature + body + ''.join(lines[func.end_lineno:])
    return {'text': new_text, 'calc': calc_call.func.id, 'param': param,
            'lines': func.end_lineno - func.lineno + 1}, ''


def verify(new_text, path):
    """Самопроверка после сборки текста."""
    try:
        tree = ast.parse(new_text)
    except SyntaxError as exc:
        return f"новый текст не парсится: {exc}"
    func = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'backtest':
            func = node
    if func is None:
        return "backtest пропал"
    if len(func.body) != 1 or not isinstance(func.body[0], ast.Return):
        return "тело backtest — не единственный return"
    call = func.body[0].value
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            and call.func.id == 'run_backtest'):
        return "backtest не возвращает run_backtest(...)"
    return ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--family', default='', help='префикс имени модуля')
    parser.add_argument('--key', action='append', default=None,
                        help='ключ реестра (модуль берётся из реестра)')
    parser.add_argument('--write', action='store_true', help='применить')
    args = parser.parse_args()

    from strategies import _registry as reg

    if args.key:
        modules = []
        for key in args.key:
            record = reg.REGISTRY.get(key)
            if record is None:
                print(f"{key}: нет в реестре")
                continue
            modules.append(str(record['module']))
    elif args.family:
        modules = sorted({str(r['module']) for r in reg.REGISTRY.values()
                          if str(r.get('module', '')).startswith(args.family)})
    else:
        raise SystemExit("укажите --family или --key")

    if not modules:
        raise SystemExit("модулей не найдено")

    done, skipped = [], []
    for module in modules:
        path = os.path.join(STRATEGIES, module + '.py')
        if not os.path.isfile(path):
            skipped.append((module, "файла нет"))
            continue
        plan, reason = plan_file(path)
        if plan is None:
            skipped.append((module, reason))
            continue
        problem = verify(plan['text'], path)
        if problem:
            skipped.append((module, f"[ОТКАЗ] {problem}"))
            continue
        print(f"  {module}: calc={plan['calc']} param={plan['param']} "
              f"строк заменено {plan['lines']}")
        if args.write:
            with open(path, 'w', encoding='utf-8', newline='') as fh:
                fh.write(plan['text'])
        done.append(module)

    print(f"\nПереведено: {len(done)}; пропущено: {len(skipped)}")
    for module, reason in skipped:
        print(f"  пропуск {module}: {reason}")
    if not args.write:
        print("\nDry-run: файлы не изменены. Для применения: --write")
    else:
        print("\nПроверка: python tools/loop_model_pilot.py --family "
              f"{args.family or '<family>'} — колонки legacy и core должны совпасть.")


if __name__ == '__main__':
    main()
