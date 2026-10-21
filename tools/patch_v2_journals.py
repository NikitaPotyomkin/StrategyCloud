"""Шаг 1 чекпойнта v2: добавить журнал сделок в легаси-циклы strategies/*.py.

Зачем: у 38 легаси-семейств (stochastic, parabolic, random_forest, logreg, adx_trend,
bb_squeeze_breakout, ...) СВОЙ цикл симуляции, не через strategies/_bt_core.py.
Без журнала сделок эти комбинации не смогут обновляться инкрементально.

Что делает для каждого файла (идемпотентно):
  1) trade_profits = []            → импорт TradeList/trade_row + trade_profits = TradeList()
  2) position = {'direction': ...} → добавляет строку _entry_i = i перед каждой (их 2: long/short)
  3) trade_profits.append(<p>)     → добавляет запись trade_row(df.index, _entry_i, i,
                                     position['direction'], <p>) в trade_profits.times
  Возврат (profit, n_trades, trade_profits) НЕ меняется: TradeList — наследник list.

Гарантии безопасности:
  - файл пропускается, если уже содержит 'TradeList()';
  - если не найдены ровно 2 места создания позиции или ровно 1 место append —
    файл НЕ трогается и попадает в отчёт «требует ручной проверки»;
  - перед изменением рядом пишется копия <файл>.bak.<timestamp>;
  - --dry-run только показывает, что было бы изменено.

Запуск (обычно один раз):
    python tools/patch_v2_journals.py --dry-run
    python tools/patch_v2_journals.py
"""

import os
import re
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRATEGIES_DIR = os.path.join(ROOT, 'strategies')

# Файлы, которые НЕ трогаем: движки уже обновлены, base.py — общий движок легаси.
SKIP_FILES = {'_bt_core.py', 'base.py', '_warmup.py', '_registry.py', '__init__.py'}

IMPORT_LINE = 'from strategies._bt_core import TradeList, trade_row  # v2: журнал сделок'
INIT_RE = re.compile(r'(?m)^(?P<ind>[ \t]*)trade_profits = \[\]')
POSITION_RE = re.compile(r'(?m)^(?P<ind>[ \t]*)position = \{')
APPEND_RE = re.compile(r'(?m)^(?P<ind>[ \t]*)trade_profits\.append\((?P<var>[^)]+)\)[ \t]*$')


def _patch_text(src):
    """Вернуть (new_src, notes). new_src is None, если файл не по шаблону."""
    notes = []

    # 1) инициализация журнала
    m = INIT_RE.search(src)
    if not m:
        return None, ['не найдено «trade_profits = []»']
    ind = m.group('ind')
    src = INIT_RE.sub(
        lambda mm: f"{ind}{IMPORT_LINE}\n{ind}trade_profits = TradeList()",
        src, count=1)

    # 2) индекс бара входа — ровно 2 места (long/short)
    pos = list(POSITION_RE.finditer(src))
    if len(pos) != 2:
        return None, [f'мест создания позиции: {len(pos)} (ожидается 2)']
    for mm in reversed(pos):  # с конца, чтобы не сбить offsets
        line_ind = mm.group('ind')
        src = src[:mm.start()] + f'{line_ind}_entry_i = i\n' + src[mm.start():]

    # 3) запись сделки в журнал — ровно 1 место
    app = list(APPEND_RE.finditer(src))
    if len(app) != 1:
        return None, [f'мест append: {len(app)} (ожидается 1)']
    mm = app[0]
    line_ind = mm.group('ind')
    var = mm.group('var').strip()
    block = (f'{line_ind}_row = trade_row(df.index, _entry_i, i, position["direction"], {var})\n'
             f'{line_ind}if _row is not None:\n'
             f'{line_ind}    trade_profits.times.append(_row)')
    src = src[:mm.end()] + '\n' + block + src[mm.end():]

    notes.append('патч применён')
    return src, notes


def main(argv):
    dry = '--dry-run' in argv
    names = sorted(n for n in os.listdir(STRATEGIES_DIR)
                   if n.endswith('.py') and n not in SKIP_FILES)
    patched, skipped, manual = [], [], []
    stamp = time.strftime('%Y%m%d_%H%M%S')

    for name in names:
        path = os.path.join(STRATEGIES_DIR, name)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                src = f.read()
        except OSError as exc:
            manual.append((name, f'не читается: {exc!r}'))
            continue

        if 'TradeList()' in src:
            skipped.append(name)
            continue
        if 'trade_profits' not in src:
            continue  # стратегия без своего цикла (идёт через _bt_core)

        new_src, notes = _patch_text(src)
        if new_src is None:
            manual.append((name, '; '.join(notes)))
            continue
        if dry:
            patched.append(name)
            continue
        try:
            shutil.copy2(path, f'{path}.bak.{stamp}')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_src)
            patched.append(name)
        except OSError as exc:
            manual.append((name, f'не записался: {exc!r}'))

    print(f'\nШаг 1 (чекпойнт v2): файлов просмотрено {len(names)}')
    print(f'  ✅ обновлено: {len(patched)}' + ('' if not patched else f" → {', '.join(patched)}"))
    print(f'  ⏭ уже были с журналом: {len(skipped)}')
    if manual:
        print(f'  ⚠️  требуют ручной проверки: {len(manual)}')
        for name, why in manual:
            print(f'     • {name}: {why}')
    if dry:
        print('\n  (--dry-run: файлы не изменялись)')
    else:
        print(f'\n  Бэкапы: strategies/<файл>.bak.{stamp}')
        print('  Дальше: py_compile в PyCharm + прогон, в логе ищем «Чекпойнт v2: журналы сделок записаны»')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
