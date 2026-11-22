"""Перевод функции backtest на общий движок strategies/_bt_core.

Два шага, чтобы не смешивать два изменения в одном замере:

  --model legacy  (шаг C) — модель прежняя (вход по close[i], обрыв сделки,
                  не закрывшейся за 49 баров), но арифметика исправлена:
                  run_backtest_legacy вычитает спред и считает P&L через
                  trade_profit (÷ tick_size). Числа становятся сравнимыми с
                  остальным реестром, модель входа не меняется.

  --model core    (шаг B) — эталонный run_backtest: вход по open[i+1] ± спред,
                  спред на выходе, обрыва по времени нет.

Инструмент заменяет ТОЛЬКО тело backtest. calc_* и предикаты check_entry /
check_exit не трогаются — сигнал остаётся тем же, что в бою.

Нестандартные формы, которые он разбирает:
  * сигнатура backtest в две строки — берётся блок от `def` до двоеточия,
    имена аргументов сверяются через ast;
  * calc_* зовётся с параметрами, собранными из param_key (p1, p2 = ...) —
    тогда перед backtest ставится обёртка _calc(df, param_key);
  * check_entry отдаёт bool вместо 'long'/'short'/None (направление теряется) —
    ставится адаптер _entry, который берёт знак curr, как делала прежняя петля.

Гейты (без них конверсия молча ломает стратегию):
  * check_entry должен отдавать строку направления либо bool при наличии в
    петле условия prev_k == 0 and curr_k == 1;
  * check_exit должен принимать (prev, curr, direction) — иначе движок его не
    позовёт;
  * для --model legacy модуль не должен реально выходить по check_exit:
    run_backtest_legacy выходит только по SL/TP, как прежние петли.

Защита: по умолчанию dry-run. С --write файл после правки обязан распарситься,
backtest обязан остаться с единственным return run_backtest*(...), сигнатура —
с теми же именами аргументов. Файлы под git: откат — git checkout -- strategies/.

Запуск:
    python tools/loop_to_core.py --model legacy --all           # план
    python tools/loop_to_core.py --model legacy --all --write   # применить
    python tools/loop_to_core.py --model core --all --write
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

FN = {'core': 'run_backtest', 'legacy': 'run_backtest_legacy'}
IMPORT_LINE = 'from strategies._bt_core import {fn}\n'

# Прежняя петля кодирует направление знаком состояния: 0→+1 это long, 0→−1 short.
RE_DIRECTIONAL_LOOP = re.compile(r'prev_k\s*==\s*0\s*and\s*curr_k\s*==\s*1')

DOC = {
    'core': '''    """Симуляция через общий движок strategies/_bt_core.run_backtest.

    Вход по open следующего бара ± спред, спред вычитается и на выходе, обрыва
    по времени нет, деньги через trade_profit (÷ tick_size). Прежняя петля
    входила по close сигнального бара, не вычитала спред, выбрасывала сделки,
    не закрывшиеся за 49 баров, и считала P&L без деления на tick_size —
    из-за этого её числа были несравнимы с остальным реестром.
    """
''',
    'legacy': '''    """Симуляция через strategies._bt_core.run_backtest_legacy (шаг C).

    Модель прежняя — вход по close сигнального бара и обрыв сделки, не
    закрывшейся за 49 баров, — но арифметика исправлена: спред вычитается,
    P&L считается через trade_profit (÷ tick_size), в trade_profits рубли.
    Без этого деньги были занижены в 1/tick_size раз (EURUSD ×1e-5) и ranking
    сравнивал несравнимое. Шаг B — замена вызова на run_backtest.
    """
''',
}

BOOL_ADAPTER = '''def _entry(prev, curr):
    """check_entry модуля отдаёт bool — направление берём из знака состояния.

    Прежняя петля входила в long при переходе 0→+1 и в short при 0→−1, а
    run_backtest ждёт 'long'/'short'/None. Булев ответ разворачиваем по curr.
    """
    if not check_entry(prev, curr):
        return None
    if curr == 1:
        return 'long'
    if curr == -1:
        return 'short'
    return None


'''


def _body(model, calc_arg, param, entry_fn):
    """Текст тела backtest — единственный return с делегированием."""
    fn = FN[model]
    return (DOC[model]
            + f"    return {fn}(df, {calc_arg}, {entry_fn}, check_exit,\n"
              f"                        {param}, sl_points, tp_points, point,\n"
              f"                        tick_value, tick_size, sim_lot, spread_points)\n")


def _wrapper(calc_src, prefix_src):
    """Обёртка _calc(df, param_key) для модулей, разбирающих param_key."""
    return ('def _calc(df, param_key):\n'
            '    """calc_* с параметрами, собранными из param_key."""\n'
            f'{prefix_src}'
            f'    return {calc_src}\n\n\n')


def _ret_kinds(value):
    """Множество типов возвращаемого выражения ('str'/'bool'/'none'/'other')."""
    if value is None:
        return {'none'}
    if isinstance(value, ast.Constant):
        if isinstance(value.value, bool):
            return {'bool'}
        if isinstance(value.value, str):
            return {'str'}
        if value.value is None:
            return {'none'}
        return {'other'}
    if isinstance(value, (ast.Compare, ast.BoolOp)):   # return prev == 0 and curr == 1
        return {'bool'}
    if isinstance(value, ast.IfExp):        # 'long' if cond else None
        return _ret_kinds(value.body) | _ret_kinds(value.orelse)
    return {'other'}


def _entry_contract(func):
    """'str' — отдаёт направление, 'bool' — True/False, '?' — разбирать вручную."""
    kinds = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Return):
            kinds |= _ret_kinds(node.value)
    if 'str' in kinds:
        return 'str'
    if 'bool' in kinds:
        return 'bool'
    return '?'


def _signature(lines, func):
    """Блок сигнатуры backtest: от `def` до строки, где скобки закрылись и есть ':'.

    Так разбирается и однострочная, и двухстрочная запись, и случай, когда
    сразу за сигнатурой идут комментарии (иначе они попадали в «сигнатуру» и
    она переставала кончаться двоеточием).
    """
    start = func.lineno - 1
    depth = 0
    for idx in range(start, min(start + 20, len(lines))):
        line = lines[idx]
        depth += line.count('(') - line.count(')')
        if depth <= 0 and line.rstrip().endswith(':'):
            return ''.join(lines[start:idx + 1])
    return ''


def _arg_names(func):
    return [a.arg for a in func.args.args]


def _prefix_needed(prefix, call):
    """Нужны ли строки перед calc_*: они готовят аргументы для вызова?"""
    targets = set()
    for stmt in prefix:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                targets.add(node.id)
    used = {n.id for n in ast.walk(call) if isinstance(n, ast.Name)}
    return bool(targets & used)


def plan_upgrade(path):
    """Шаг B для файлов, уже переведённых шагом C: legacy-движок → эталонный.

    Тело после шага C — единственное делегирование, поэтому менять надо только
    три вещи: имя функции в вызове, строку импорта и докстринг. calc_*,
    аргументы и предикаты не трогаются, ast-хирургия не нужна.
    """
    with open(path, 'r', encoding='utf-8', newline='') as fh:
        text = fh.read()
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return None, f"не парсится: {exc}"

    func = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'backtest':
            func = node
    if func is None:
        return None, "нет def backtest"

    legacy_call = None
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == 'run_backtest_legacy':
            legacy_call = node
    if legacy_call is None:
        return None, "не на run_backtest_legacy"

    entry_fn = None
    if len(legacy_call.args) >= 3 and isinstance(legacy_call.args[2], ast.Name):
        entry_fn = legacy_call.args[2].id
    calc_arg = None
    if len(legacy_call.args) >= 2 and isinstance(legacy_call.args[1], ast.Name):
        calc_arg = legacy_call.args[1].id

    new_text = text
    imp = 'from strategies._bt_core import run_backtest_legacy'
    if imp in new_text:
        new_text = new_text.replace(imp, 'from strategies._bt_core import run_backtest')
    if DOC['legacy'] in new_text:
        new_text = new_text.replace(DOC['legacy'], DOC['core'])
    new_text = new_text.replace('run_backtest_legacy(', 'run_backtest(')

    return {'text': new_text, 'calc': calc_arg or '-', 'param': '-',
            'args': _arg_names(func), 'wrapper': False, 'adapter': False,
            'entry': entry_fn, 'upgrade': True,
            'lines': func.end_lineno - func.lineno + 1}, ''


def plan_file(path, model):
    """(план, причина_отказа). План — dict с текстом и метаданными."""
    with open(path, 'r', encoding='utf-8', newline='') as fh:
        text = fh.read()
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return None, f"не парсится: {exc}"

    func = None
    defs = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs[node.name] = node
            if node.name == 'backtest':
                func = node
    if func is None:
        return None, "нет def backtest на уровне модуля"
    for required in ('check_entry', 'check_exit'):
        if required not in defs:
            return None, f"нет {required} (реестр может звать state_*)"

    # Проверяем ВЫЗОВ, а не упоминание: в check_entry почти каждого файла есть
    # комментарий «... for engine run_backtest», и поиск по подстроке давал
    # ложный пропуск «уже переведён».
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in ('run_backtest', 'run_backtest_legacy'):
            if node.func.id == 'run_backtest_legacy':
                if model == 'core':
                    return plan_upgrade(path)
                return None, "уже на шаге C (run_backtest_legacy)"
            return None, "уже делегирует в движок"

    # ── контракт предикатов ──
    contract = _entry_contract(defs['check_entry'])
    entry_fn = 'check_entry'
    needs_adapter = False
    if contract == 'bool':
        if not RE_DIRECTIONAL_LOOP.search(text):
            return None, ("check_entry отдаёт bool, а в петле нет условия "
                          "prev_k == 0 and curr_k == 1 — направление не восстановить")
        if '_entry' in defs:
            return None, "в модуле уже есть _entry — имя адаптера занято"
        entry_fn, needs_adapter = '_entry', True
    elif contract != 'str':
        return None, "check_entry отдаёт не строку направления — нужен ручной разбор"

    exit_func = defs['check_exit']
    n_pos = len(exit_func.args.args)
    n_def = len(exit_func.args.defaults)
    if n_pos < 3 or (n_pos - n_def) > 3:
        return None, (f"check_exit несовместим с движком: позиционных {n_pos}, "
                      f"из них с умолчанием {n_def}")

    # Модель C (run_backtest_legacy) выходит только по SL/TP — как прежние
    # петли поколения B. Если петля модуля реально зовёт check_exit, шаг C
    # изменил бы смысл выхода, поэтому такие файлы идут сразу шагом B.
    uses_exit = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == 'check_exit' for n in ast.walk(func))
    if model == 'legacy' and uses_exit:
        return None, ("петля выходит по check_exit — модель C её не вызывает; "
                      "переводить сразу --model core")

    # ── вызов calc_* и его аргументы ──
    call = None
    assign_idx = None
    for idx, stmt in enumerate(func.body):
        if not isinstance(stmt, ast.Assign):
            continue
        if not (len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id == 'df'):
            continue
        value = stmt.value
        if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                and value.func.id.startswith('calc_')):
            call, assign_idx = value, idx
            break
    if call is None:
        return None, "в backtest нет оператора df = calc_*(...)"

    prefix = func.body[:assign_idx]
    for stmt in prefix:
        if any(isinstance(n, ast.Name) and n.id == 'df' for n in ast.walk(stmt)):
            return None, "подготовка перед calc_* использует df — нужен ручной разбор"

    args = call.args[1:]
    calc_arg = None
    if len(args) == 1:
        arg = args[0]
        if isinstance(arg, ast.Name) and arg.id == 'param_key':
            calc_arg = 'param_key'
        elif (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name)
              and arg.func.id in ('int', 'float')
              and len(arg.args) == 1
              and isinstance(arg.args[0], ast.Name)
              and arg.args[0].id == 'param_key'):
            calc_arg = f'{arg.func.id}(param_key)'

    # Строки перед calc_* нужны, только если из них берутся аргументы вызова.
    if not _prefix_needed(prefix, call):
        prefix = []

    needs_wrapper = calc_arg is None
    if needs_wrapper and not prefix:
        try:
            shown = ', '.join(ast.unparse(a) for a in args) or '<нет>'
        except Exception:                      # noqa: BLE001 — только для сообщения
            shown = '?'
        return None, (f"calc_* вызывается нестандартно и param_key не разбирается: "
                      f"аргументов {len(args)}, param={shown}")
    if needs_wrapper and '_calc' in defs:
        return None, "в модуле уже есть _calc — имя обёртки занято"

    lines = text.splitlines(keepends=True)
    # Сигнатура — весь блок от `def backtest(` до строки с двоеточием: в шести
    # модулях mr_ она записана в две строки.
    # Сигнатуру берём по балансу скобок (одна или две строки, плюс комментарии).
    signature = _signature(lines, func)
    if not signature.rstrip().endswith(':'):
        return None, "не удалось выделить сигнатуру backtest"

    head = ''.join(lines[:func.lineno - 1])
    import_line = IMPORT_LINE.format(fn=FN[model])
    if import_line not in head:
        head += import_line
    if needs_adapter:
        head += BOOL_ADAPTER

    if needs_wrapper:
        prefix_src = ''.join(
            ''.join(lines[stmt.lineno - 1:stmt.end_lineno]) for stmt in prefix)
        calc_src = ast.get_source_segment(text, call)
        if not calc_src:
            return None, "не удалось прочитать вызов calc_* из исходника"
        head += _wrapper(calc_src, prefix_src)
        calc_arg = '_calc'
        param = 'param_key'
    else:
        param = calc_arg

    new_text = (head + signature + _body(model, call.func.id if not needs_wrapper
                                         else '_calc', param, entry_fn)
                + ''.join(lines[func.end_lineno:]))

    return {'text': new_text, 'calc': call.func.id, 'param': param,
            'args': _arg_names(func), 'wrapper': needs_wrapper,
            'adapter': needs_adapter, 'entry': entry_fn,
            'lines': func.end_lineno - func.lineno + 1}, ''


def verify(new_text, model, orig_args, wrapper, adapter, entry_fn):
    """Самопроверка собранного текста. Пустая строка — всё хорошо."""
    try:
        tree = ast.parse(new_text)
    except SyntaxError as exc:
        return f"новый текст не парсится: {exc}"

    func = None
    defined = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            defined.add(node.name)
            if node.name == 'backtest':
                func = node
    if func is None:
        return "backtest пропал"
    if _arg_names(func) != orig_args:
        return (f"имена аргументов backtest изменились: "
                f"{_arg_names(func)} != {orig_args}")

    # Тело = необязательный докстринг + единственный return.
    body = func.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return "тело backtest — не единственный return"
    call = body[0].value
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            and call.func.id == FN[model]):
        return f"backtest не возвращает {FN[model]}(...)"
    # Второй аргумент движка — calc (обёртка или сам calc_*), третий — предикат входа.
    if len(call.args) < 3:
        return "вызов движка короче трёх аргументов"
    calc_node, entry_node = call.args[1], call.args[2]
    if not (isinstance(calc_node, ast.Name)
            and (calc_node.id.startswith('calc_') or calc_node.id == '_calc')):
        return "второй аргумент движка — не calc"
    if not (isinstance(entry_node, ast.Name) and entry_node.id == entry_fn):
        return f"третий аргумент движка — не {entry_fn}"
    if wrapper and '_calc' not in defined:
        return "обёртка _calc не появилась"
    if adapter and '_entry' not in defined:
        return "адаптер _entry не появился"
    return ''


def collect_modules(args):
    """Список модулей по --family / --key / --all."""
    from strategies import _registry as reg

    if args.key:
        modules = []
        for key in args.key:
            record = reg.REGISTRY.get(key)
            if record is None:
                print(f"{key}: нет в реестре")
                continue
            modules.append(str(record['module']))
        return sorted(set(modules))
    if args.family:
        return sorted({str(r['module']) for r in reg.REGISTRY.values()
                       if str(r.get('module', '')).startswith(args.family)})
    return sorted({str(r['module']) for r in reg.REGISTRY.values()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=('legacy', 'core'), default='legacy',
                        help='legacy — шаг C (сравнимые деньги), core — шаг B')
    parser.add_argument('--family', default='', help='префикс имени модуля')
    parser.add_argument('--key', action='append', default=None,
                        help='ключ реестра (модуль берётся из реестра)')
    parser.add_argument('--all', action='store_true', help='все модули реестра')
    parser.add_argument('--write', action='store_true', help='применить')
    args = parser.parse_args()

    if not (args.all or args.family or args.key):
        raise SystemExit("укажите --family, --key или --all")

    modules = collect_modules(args)
    if not modules:
        raise SystemExit("модулей не найдено")

    done, skipped = [], []
    for module in modules:
        path = os.path.join(STRATEGIES, module + '.py')
        if not os.path.isfile(path):
            skipped.append((module, "файла нет"))
            continue
        plan, reason = plan_file(path, args.model)
        if plan is None:
            skipped.append((module, reason))
            continue
        problem = verify(plan['text'], args.model, plan['args'], plan['wrapper'],
                         plan['adapter'], plan['entry'])
        if problem:
            skipped.append((module, f"[ОТКАЗ] {problem}"))
            continue
        marks = (' +_calc' if plan['wrapper'] else '') + \
                (' +_entry' if plan['adapter'] else '')
        print(f"  {module}: calc={plan['calc']} param={plan['param']}{marks}, "
              f"строк заменено {plan['lines']}")
        if args.write:
            with open(path, 'w', encoding='utf-8', newline='') as fh:
                fh.write(plan['text'])
        done.append(module)

    print(f"\nПереведено: {len(done)}; пропущено: {len(skipped)} (model={args.model})")
    for module, reason in skipped:
        print(f"  пропуск {module}: {reason}")
    if not args.write:
        print("\nDry-run: файлы не изменены. Для применения: --write")
    else:
        print("\nДальше: python tools/loop_audit.py — у переведённых не должно "
              "остаться 'timeout50'/'unscaled'.")


if __name__ == '__main__':
    main()
