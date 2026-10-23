"""Разовая правка вкладок дэшборда (одноразовый патч).

Что делает:
  1) удаляет вкладку «3D Landscape» ВМЕСТЕ с её кодом (секция `with tab_3d:`);
  2) удаляет вкладку «Pipeline» ВМЕСТЕ с её кодом (секция `with tab_pipeline:`);
  3) переписывает вызов st.tabs: Strategy Tree — вторым номером (сразу после
     Overview), «Steering Wheel» → «Wheel»;
  4) переписывает FinStatement: раскрывается МЕСЯЦ, дни внутри — атомарные строки;
  5) переименовывает заголовок секции STEERING WHEEL → WHEEL.
     (Ноябрь, Декабрь, Январь — пустые заготовки на будущее);

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

# ── FinStatement: секция переписывается целиком по границам секций ──
# Раскрывается МЕСЯЦ (st.expander), внутри — таблица, где день = атомарная строка
# (число · день недели · PnL · trades · cum). Будущие месяцы (Ноябрь, Декабрь,
# Январь) добавляются пустыми заготовками. Текст шаблона начинается с начала
# строки: отступы внутри — отступы дэшборда, а не скрипта.
FS_TITLE = '#  FINSTATEMENT'
FS_SECTION = '''# ═══════════════════════════════════════════════════════════════
#  FINSTATEMENT — P&L по месяцам (день = атомарная строка)
# ═══════════════════════════════════════════════════════════════
with tab_finstatement:
    st.markdown("### FinStatement — daily P&L by month")
    try:
        # Окно берём ШИРЕ слайдера: от FUND_START_DATE до сегодня (в днях).
        _fs_start = datetime.strptime(str(FUND_START_DATE), '%Y-%m-%d').date()
        _fs_today = (pd.Timestamp.now('UTC') + pd.Timedelta(hours=_SRV_OFFSET_H)).date()
        _fs_n = max(1, (_fs_today - _fs_start).days + 1)
        _fs_data = load_dashboard_data(_fs_n) or {}
        _fs_df = _fs_data.get('trades_df')
        if _fs_df is None or _fs_df.empty:
            st.info("No closed trades since the fund start.")
        else:
            _fs = _fs_df.copy()
            _fs['date'] = (pd.to_datetime(_fs['time'], unit='s', utc=True)
                           + pd.Timedelta(hours=_SRV_OFFSET_H)).dt.date
            _by = _fs.groupby('date').agg(pnl=('profit_net', 'sum'),
                                          trades=('profit_net', 'size')).reset_index()
            # Дни без сделок показываем нулём, а не пропускаем: иначе в календаре «дырки».
            _cal = pd.DataFrame({'date': [d.date() for d in pd.date_range(_fs_start, periods=_fs_n)]})
            _by = _cal.merge(_by, on='date', how='left')
            _by['pnl'] = _by['pnl'].fillna(0.0).round(0).astype(int)
            _by['trades'] = _by['trades'].fillna(0).astype(int)
            _by['cum'] = _by['pnl'].cumsum()
            _by['wd'] = [_RU_WEEKDAYS[d.weekday()] for d in _by['date']]
            _by['ym'] = [(d.year, d.month) for d in _by['date']]
            _cols = [c for c in ('symbol', 'param_key', 'volume', 'profit_net') if c in _fs.columns]
            st.caption(f"Fund start {_fs_start.strftime('%d.%m.%Y')} · {_fs_n} days · "
                       f"total P&L {int(_fs['profit_net'].sum()):,} RUB (net of swap and commission)")

            # ── Месяц раскрывается, дни внутри — атомарные строки таблицы ──
            for _mi, ((_y, _m), _g) in enumerate(_by.groupby('ym', sort=True), start=1):
                _g = _g.reset_index(drop=True)
                _mpnl = int(_g['pnl'].sum())
                _mtr = int(_g['trades'].sum())
                _mtitle = (f"{_mi:>2}. {_RU_MONTHS[_m - 1].capitalize()} {_y} — "
                           f"P&L {_mpnl:,} RUB · trades {_mtr} · cum {int(_g['cum'].iloc[-1]):,} RUB")
                with st.expander(_mtitle, expanded=((_y, _m) == _by['ym'].iloc[-1])):
                    _days = pd.DataFrame({
                        '#': range(1, len(_g) + 1),
                        'day': [d.strftime('%d') for d in _g['date']],
                        'weekday': list(_g['wd']),
                        'PnL': _g['pnl'],
                        'trades': _g['trades'],
                        'cum': _g['cum'],
                    }).set_index('#')
                    st.dataframe(_days, use_container_width=True)
                    _mreg = _fs[_fs['date'].isin(list(_g['date']))]
                    if not _mreg.empty and _cols:
                        st.caption(f"Trades of month: {len(_mreg)}")
                        st.dataframe(_mreg[_cols].rename(columns={'profit_net': 'PnL'}),
                                     use_container_width=True)

            # ── Пустые заготовки на будущие месяцы: Ноябрь, Декабрь, Январь ──
            _ly, _lm = _by['ym'].iloc[-1]
            for _k in (1, 2, 3):
                _tot = _lm + _k
                _fy, _fm = _ly + (_tot - 1) // 12, (_tot - 1) % 12 + 1
                with st.expander(f"{_RU_MONTHS[_fm - 1].capitalize()} {_fy} — no data yet"):
                    st.caption("Месяц ещё не начался — сделок нет.")
    except Exception as _e:
        st.caption(f"⚠ FinStatement недоступен: {_e!r}")'''

# Новый порядок вкладок: Strategy Tree — вторым (после Overview).
TAB_VARS = ('tab_overview, tab_tree, tab_finstatement, tab_daily, tab_risk, tab_strategies, '
            'tab_steering, tab_backtest')
TAB_LABELS = ('Overview', 'Strategy Tree', 'FinStatement', 'Daily Plan', 'Risk', 'Strategies',
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
    """[(индекс строки-рамки, заголовок)] для секций `# ═══ / #  NAME / # ═══ / with tab_*:`.

    Вкладки, уже убранные из дэшборда, помечены `if False:` вместо `with tab_*` —
    они тоже считаются секциями, чтобы код можно было удалить физически.
    """
    out = []
    for i in range(1, len(lines) - 3):
        s = lines[i].strip()
        if (s.startswith('#') and not _is_box(lines[i])
                and _is_box(lines[i - 1]) and _is_box(lines[i + 1])
                and lines[i + 2].lstrip().startswith(('with tab_', 'if False:'))):
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

    # ── 3) FinStatement: месяц — expander, дни — атомарные строки таблицы ──
    # Границы ищем по содержимому: от рамки секции до следующей строки-рамки
    # (а не до следующей распознанной секции — между ними бывают «пустые»
    # заголовки вроде RISK без тела, их съедать нельзя).
    # FinStatement уже приведён к нужному виду ПРЯМО в dashboard.py (месяцы-по-годам,
    # компактная HTML-таблица). Шаблон ниже оставлен только как справка — не применяем,
    # иначе он откатит UI-правки назад. Оставляем [] → шаг пропускается.
    _secs = []
    _tgt = next((k for k, (_, t) in enumerate(_secs) if t.startswith(FS_TITLE)), None)
    if _tgt is None:
        pass  # FinStatement уже актуален — шаблон не применяем (не трогаем report)
    else:
        _a = _secs[_tgt][0]
        _b = len(lines)
        for _i in range(_a + 3, len(lines)):
            if _is_box(lines[_i]):
                _b = _i
                break
        while _b > _a and not lines[_b - 1].strip():     # пустые строки вернём шаблоном
            _b -= 1
        _tpl = FS_SECTION.replace('\r\n', '\n').replace('\r', '\n').rstrip('\n').split('\n')
        _new = [ln + nl for ln in _tpl] + [nl, nl]
        if ''.join(lines[_a:_b]).strip() != ''.join(_new).strip():
            lines[_a:_b] = _new
            report.append(f'  - FinStatement переписан: месяц = expander, дни — строки ({len(_tpl)} строк)')

    # ── 3б) Мёртвая ветка старого подневного FinStatement (`elif False: …`) ──
    # Ветка выключена флагом; удаляем её физически, чтобы код не копился.
    # Границы — по содержимому: от `elif False:` до `else:` того же уровня (8 пробелов).
    _d0 = _d1 = None
    for _i, _ln in enumerate(lines):
        if _d0 is None and _ln.strip().startswith('elif False:'):
            _d0 = _i
        elif _d0 is not None and _ln.rstrip() == '        else:':
            _d1 = _i
            break
    if _d0 is not None and _d1 is not None and _d1 > _d0:
        report.append(f'  - FinStatement: удалена выключенная подневная ветка ({_d1 - _d0} строк)')
        lines[_d0:_d1] = []

    # ── 4) Переименования (заголовок секции + подпись) ──
    src = ''.join(lines)
    for old, new in RENAMES:
        if old in src:
            src = src.replace(old, new)
            report.append(f'  - переименовано: {old!r} → {new!r}')

    n_after = len(src.splitlines())
    if not report:
        print('[tabs] нечего менять — файл уже в нужном виде (идемпотентно).')
        return 0

    # ── 5) Проверка синтаксиса ДО записи ──
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
