"""Разовая правка вкладок дэшборда (одноразовый патч).

Что делает:
  1) удаляет вкладку «3D Landscape» ВМЕСТЕ с её кодом (секция `with tab_3d:`);
  2) удаляет вкладку «Pipeline» ВМЕСТЕ с её кодом (секция `with tab_pipeline:`);
  3) переписывает вызов st.tabs: Strategy Tree — вторым номером (сразу после
     Overview), «Steering Wheel» → «Wheel»;
  4) переименовывает заголовок секции STEERING WHEEL → WHEEL.

Почему отдельным скриптом, а не правкой на месте:
    MCP-инструмент replace_text_in_file умеет заменять только literal-подстроку
    ВНУТРИ ОДНОЙ строки (многострочный search не поддерживается), а здесь нужно
    именно УДАЛИТЬ ~120 строк кода. Скрипт делает это по границам секций, а не по
    номерам строк, поэтому переживает любые сдвиги в файле.

Безопасность:
  * идемпотентно: повторный запуск ничего не меняет;
  * синтаксис нового файла проверяется compile() ДО записи;
  * рядом кладётся бэкап dashboard.py.bak.YYYYMMDD_HHMMSS;
  * строки не «затираются» по номерам — границы ищутся по содержимому.

Запуск:
  python tools/dashboard_tabs.py             # применить
  python tools/dashboard_tabs.py --dry-run   # только показать план
"""
import argparse
import datetime
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASH = os.path.join(BASE, 'dashboard.py')

# Новый порядок вкладок: Strategy Tree — вторым (после Overview).
TAB_VARS = ('tab_overview, tab_tree, tab_daily, tab_risk, tab_strategies, '
            'tab_steering, tab_backtest')
TAB_LABELS = ('Overview', 'Strategy Tree', 'Daily Plan', 'Risk', 'Strategies',
              'Wheel', 'Backtest')

# Секции под удаление (заголовок внутри рамки `# ═══ / #  NAME / # ═══`).
DROP_SECTIONS = ('#  3D LANDSCAPE', '#  PIPELINE')

# Переименование боевой вкладки штурвала.
RENAMES = (
    ('#  STEERING WHEEL', '#  WHEEL'),
    ('###Wheel — Quota by Family', '### Wheel — Quota by Family'),
)


def _is_box(line):
    """Строка-рамка секции: '# ═══════...'."""
    s = line.strip()
    return s.startswith('# ═')


def _section_starts(lines):
    """[(индекс строки-рамки, заголовок)] для секций `# ═══ / #  NAME / # ═══ / with tab_*:`."""
    out = []
    for i in range(1, len(lines) - 3):
        s = lines[i].strip()
        if (s.startswith('#') and not _is_box(lines[i])
                and _is_box(lines[i - 1]) and _is_box(lines[i + 1])
                and lines[i + 2].lstrip().startswith('with tab_')):
            out.append((i - 1, s))
    return out


def _find_tabs_block(lines):
    """(i0, i1) — границы вызова st.tabs(...) или (None, None)."""
    i0 = i1 = None
    for i, ln in enumerate(lines):
        if i0 is None and ln.lstrip().startswith('tab_overview,'):
            i0 = i
        elif i0 is not None and ln.strip() == '])':
            i1 = i
            break
    return i0, i1


def main():
    ap = argparse.ArgumentParser(description='Разовая правка вкладок дэшборда')
    ap.add_argument('--dry-run', action='store_true', help='только показать план, не писать')
    args = ap.parse_args()

    if not os.path.exists(DASH):
        print(f'[tabs] нет файла: {DASH}')
        return 1

    with open(DASH, 'r', encoding='utf-8', newline='') as f:
        raw = f.read()
    nl = '\r\n' if '\r\n' in raw else '\n'
    lines = raw.splitlines(keepends=True)
    n_before = len(lines)
    report = []

    # ── 1) Секции 3D Landscape и Pipeline — целиком, вместе с кодом ──
    for title in DROP_SECTIONS:
        secs = _section_starts(lines)
        tgt = next((k for k, (_, t) in enumerate(secs) if t == title), None)
        if tgt is None:
            continue
        a = secs[tgt][0]
        b = secs[tgt + 1][0] if tgt + 1 < len(secs) else len(lines)
        while a > 0 and not lines[a - 1].strip():      # вбираем пустые строки сверху
            a -= 1
        while b > a and not lines[b - 1].strip():      # и снизу
            b -= 1
        report.append(f'  - удалена секция {title.strip()}: {b - a} строк')
        lines[a:b] = [nl, nl]                          # ровно 2 пустые строки между секциями

    # ── 2) Вызов st.tabs: порядок и названия ──
    i0, i1 = _find_tabs_block(lines)
    if i0 is not None and i1 is not None:
        block = [f'{TAB_VARS} = st.tabs([{nl}']
        block += [f'    "{lab}",{nl}' for lab in TAB_LABELS]
        block.append(f']){nl}')
        if ''.join(lines[i0:i1 + 1]) != ''.join(block):
            lines[i0:i1 + 1] = block
            report.append('  - st.tabs переписан: Strategy Tree — 2-й, "Steering Wheel" → "Wheel"')
    else:
        report.append('  ! вызов st.tabs не найден — пропущен')

    # ── 3) Переименования (заголовок секции + подпись) ──
    src = ''.join(lines)
    for old, new in RENAMES:
        if old in src:
            src = src.replace(old, new)
            report.append(f'  - переименовано: {old!r} → {new!r}')

    n_after = len(src.splitlines())
    if not report:
        print('[tabs] нечего менять — файл уже в нужном виде (идемпотентно).')
        return 0

    # ── 4) Проверка синтаксиса ДО записи ──
    try:
        compile(src, DASH, 'exec')
    except SyntaxError as exc:
        print(f'[tabs] ОТМЕНА: новый файл не компилируется: {exc}')
        return 2

    print(f'[tabs] {DASH}')
    for line in report:
        print(line)
    print(f'  - строк: {n_before} → {n_after}')

    if args.dry_run:
        print('[tabs] --dry-run: файл не изменён.')
        return 0

    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = f'{DASH}.bak.{stamp}'
    try:
        with open(backup, 'w', encoding='utf-8', newline='') as f:
            f.write(raw)
    except OSError as exc:
        print(f'[tabs] ОТМЕНА: не удалось создать бэкап: {exc!r}')
        return 2
    with open(DASH, 'w', encoding='utf-8', newline='') as f:
        f.write(src)
    print(f'[tabs] готово. Бэкап: {os.path.basename(backup)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
