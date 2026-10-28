"""Вкладка Roadmap — все модули strategies/*.py и СЛОИ их подключения.

Зачем: одна таблица вместо спора «подключено или нет». Каждая колонка — отдельный
слой пайплайна, и по каждой строке видно, докуда модуль дошёл.

Слои (слева направо):
  Standalone   — файл модуля существует в strategies/            (✓ у всех)
  calc_*       — функция расчёта сигнала внутри модуля
  entry / exit — check_entry / check_exit (live-контракт реестра)
  backtest     — функция backtest(...) внутри модуля
  Реестр       — ключ в strategies/_registry.py → REGISTRY (--/ключ)
  Батч         — ключ в ENABLED_BATCH (участвует в ночном пересчёте)
  Комб./симв.  — параметризаций × SL × TP (только для реестра)
  Native       — модуль импортируется из functions.py (родная сетка семейств)
  Семейство    — ключ семейства родной сетки (если удалось сопоставить)
  В плане      — тип есть в journals/active_state.json (торговый план)
  Позиция      — по этому типу в плане есть открытая позиция

Всё считается на месте (файлы + реестр + active_state.json), поэтому таблица
не расходится с кодом: добавили модуль — появилась строка с ✓ Standalone и
пустыми слоями ниже, и сразу видно, чего не хватает.
"""

from __future__ import annotations

import json
import os
import re

import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
STRAT_DIR = os.path.join(HERE, 'strategies')
JOURNALS_DIR = os.path.join(HERE, 'journals')

# Файлы, которые не являются стратегиями: показываем внизу таблицы, чтобы
# ничего не «пропадало» из списка папки.
INFRA = {'__init__.py', 'base.py', '_bt_core.py', '_calc_cache.py', '_registry.py'}

COL_TEXT = '#C9D1D9'
COL_MUTED = '#6E7681'
COL_GREEN_LT = '#3FB950'
COL_AMBER = '#D29922'
COL_BLUE = '#58A6FF'
COL_BG = '#0D1117'
COL_PANEL = '#161B22'
COL_BORDER = '#21262D'

_CSS = """
<style>
.rdm-wrap { overflow:auto; max-height:72vh; border:1px solid #21262D; border-radius:6px; }
table.rdm { border-collapse:collapse; font-size:0.8rem; width:100%; }
table.rdm th, table.rdm td { padding:0.2rem 0.5rem; white-space:nowrap;
        border-bottom:1px solid #21262D; }
table.rdm thead th { position:sticky; top:0; z-index:2; background:#161B22;
        color:#8B949E; font-size:0.66rem; font-weight:600; text-transform:uppercase;
        letter-spacing:0.05em; text-align:center; border-bottom:1px solid #30363D;
        padding-top:0.45rem; padding-bottom:0.4rem; }
table.rdm th.left, table.rdm td.left { text-align:left; }
table.rdm td.mono { font-family:'SF Mono','Consolas',monospace; }
table.rdm tbody tr:hover td { background:#161B22; }
table.rdm tr.inf td { color:#6E7681; }
table.rdm tr.gap td.mono { color:#C9D1D9; }
.rdm-stats { display:flex; flex-wrap:wrap; gap:34px; align-items:flex-end;
        margin:0.1rem 0 0.9rem 0; }
.rdm-stats .lbl { font-size:0.68rem; text-transform:uppercase; letter-spacing:0.07em;
        color:#8B949E; margin-bottom:0.2rem; }
.rdm-stats .val { font-size:1.7rem; font-weight:700; line-height:1.1;
        font-family:'SF Mono','Consolas',monospace; }
</style>
"""


# ═══════════════════════════ ИСТОЧНИКИ ДАННЫХ ═══════════════════════════
def _read(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ''


def _load_registry():
    """(REGISTRY, ENABLED_BATCH). Без побочных эффектов: модуль только объявляет данные."""
    try:
        import strategies._registry as reg
        return dict(getattr(reg, 'REGISTRY', {}) or {}), set(getattr(reg, 'ENABLED_BATCH', ()) or ())
    except Exception:
        return {}, set()


def _native_modules() -> set:
    """Модули, которые импортирует functions.py (родная сетка семейств)."""
    src = _read(os.path.join(HERE, 'functions.py'))
    return set(re.findall(r"from\s+strategies\.(\w+)\s+import", src))


def _native_family_map() -> dict:
    """module -> ключ семейства родной сетки.

    Сопоставление идёт по коду functions.py: обёртка `def _backtest_X(...)` знает
    свой модуль (`from strategies.M import`), а в ветке воркера
    `if not test_strategy or test_strategy == 'FAM':` вызывается `_backtest_X`.
    Парсинг мягкий: не сложилось — колонка покажет «—», таблица не падает.
    """
    src = _read(os.path.join(HERE, 'functions.py'))
    if not src:
        return {}
    wrap2mod = {}
    for chunk in src.split('\ndef ')[1:]:
        head = chunk.split('(')[0].strip()
        if not head.startswith('_backtest_'):
            continue
        m = re.search(r"from\s+strategies\.(\w+)\s+import", chunk)
        if m:
            wrap2mod[head] = m.group(1)
    fam2mod = {}
    for m in re.finditer(
            r"test_strategy\s*==\s*'(\w+)':(.*?)(?=# ─|if not test_strategy|def |\Z)",
            src, re.S):
        fam, body = m.group(1), m.group(2)
        w = re.search(r"(_backtest_\w+)", body)
        if w and w.group(1) in wrap2mod:
            fam2mod.setdefault(wrap2mod[w.group(1)], fam)
    return fam2mod


def _plan_state():
    """(типы в плане, типы с открытой позицией) из journals/active_state.json."""
    path = os.path.join(JOURNALS_DIR, 'active_state.json')
    types, open_types = set(), set()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for s in data.get('strategies') or []:
            t = s.get('type') or s.get('family')
            if not t:
                continue
            types.add(str(t))
            if s.get('has_position'):
                open_types.add(str(t))
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return types, open_types


def _run_facts():
    """family → факты ПОСЛЕДНЕГО прогона (trades_db.family_status).

    family_status — снимок после рэнкинга, одна строка на (symbol, family).
    Для модуля сворачиваем по всем символам: на скольких участвует, сколько
    комбинаций запланировано и реально посчитано, где ready_to_trade = 1.

    Возвращает (dict, 'YYYY-MM-DD HH:MM' снимка). Нет БД/таблицы — ({}, '').
    """
    facts, snap = {}, ''
    try:
        import trades_db as _tdb
        con = _tdb.connect(readonly=True)
    except Exception:
        return {}, ''
    try:
        for r in con.execute(
                "SELECT family, label, combos_planned, combos_cached, "
                "participates, ready_to_trade, snapshot_at FROM family_status"):
            fam = str(r['family'] or '')
            if not fam:
                continue
            f = facts.setdefault(fam, {
                'family': fam, 'label': str(r['label'] or ''),
                'planned': 0, 'cached': 0, 'symbols': 0, 'ready': 0, 'part': 0,
            })
            f['symbols'] += 1
            f['planned'] += int(r['combos_planned'] or 0)
            f['cached'] += int(r['combos_cached'] or 0)
            f['ready'] += 1 if r['ready_to_trade'] else 0
            f['part'] += 1 if r['participates'] else 0
            snap = str(r['snapshot_at'] or snap)
    except Exception:
        return facts, snap
    finally:
        try:
            con.close()
        except Exception:
            pass
    # ярлык как второй ключ поиска (реестр пишет в план label, а не ключ)
    for _fam, _f in list(facts.items()):
        _lab = _f.get('label') or ''
        if _lab and _lab not in facts:
            facts[_lab] = _f
    return facts, snap[:16].replace('T', ' ')


def _sl_tp_counts():
    """Сколько значений SL и TP в сетке config (для счёта комбинаций)."""
    try:
        from config import StrategyParams
        sp = StrategyParams()
        return max(1, len(sp.sl_points_list)), max(1, len(sp.tp_points_list))
    except Exception:
        return 3, 3


_CALC_RE = re.compile(r"^def\s+(calc_\w+)\s*\(", re.M)


@st.cache_data(show_spinner=False, ttl=120)
def _scan():
    """Полная инвентаризация: список строк + сводка. Кэш 2 мин (файлы меняются деплоем)."""
    registry, enabled = _load_registry()
    mod2keys = {}
    for key, ent in registry.items():
        mod = str((ent or {}).get('module') or '')
        if mod:
            mod2keys.setdefault(mod, []).append(key)
    native_mods = _native_modules()
    native_fam = _native_family_map()
    plan_types, plan_open = _plan_state()
    run_facts, run_snap = _run_facts()
    n_sl, n_tp = _sl_tp_counts()

    try:
        names = sorted(n for n in os.listdir(STRAT_DIR) if n.endswith('.py'))
    except OSError:
        names = []

    rows = []
    for fname in names:
        name = fname[:-3]
        src = _read(os.path.join(STRAT_DIR, fname))
        calc = _CALC_RE.search(src)
        keys = mod2keys.get(name, [])
        key = keys[0] if keys else ''
        ent = registry.get(key) or {}
        grid = ent.get('grid') or []
        combos = len(grid) * n_sl * n_tp if grid else 0
        is_reg = bool(key)
        is_enabled = bool(key) and key in enabled
        is_native = name in native_mods
        fam = native_fam.get(name, '')
        _aliases = {a for a in (key, str(ent.get('label') or ''), fam) if a}
        # План помечает тип ключом реестра, ярлыком либо (для родной сетки) ключом
        # семейства — проверяем все три, иначе native-модули давали ложный «—».
        in_plan = bool(_aliases & plan_types)
        has_pos = bool(_aliases & plan_open)
        # Прогон (ФАКТ): сворачиваем family_status по всем символам. Совпадение —
        # по ключу реестра, ярлыку или родному семейству; identity — family-строка,
        # иначе один модуль мог бы посчитаться дважды (ключ + ярлык).
        _rkeys = {run_facts[a]['family'] for a in _aliases if a in run_facts}
        _rsym = _rplanned = _rcached = _rready = _rpart = 0
        for _fk in _rkeys:
            _rf = run_facts[_fk]
            _rsym += int(_rf['symbols'])
            _rplanned += int(_rf['planned'])
            _rcached += int(_rf['cached'])
            _rready += int(_rf['ready'])
            _rpart += int(_rf['part'])
        _rcov = (100.0 * _rcached / _rplanned) if _rplanned > 0 else None
        rows.append({
            'file': fname,
            'module': name,
            'infra': fname in INFRA,
            'calc': calc.group(1) if calc else '',
            'entry': 'def check_entry' in src,
            'exit': 'def check_exit' in src,
            'bt': 'def backtest' in src,
            'key': key,
            'label': str(ent.get('label') or ''),
            'reg': is_reg,
            'enabled': is_enabled,
            'combos': combos,
            'native': is_native,
            'fam': fam,
            'plan': in_plan,
            'pos': has_pos,
            'rsym': _rsym,
            'rplanned': _rplanned,
            'rcached': _rcached,
            'rready': _rready,
            'rpart': _rpart,
            'rcov': _rcov,
            'bytes': len(src),
        })

    # Порядок: родные → реестр → кандидаты; инфраструктура всегда в конце.
    def _ord(r):
        tier = 0 if r['native'] else (1 if r['reg'] else 2)
        return (1 if r['infra'] else 0, tier, r['module'])

    rows.sort(key=_ord)

    stat = {
        'files': len(rows),
        'infra': sum(1 for r in rows if r['infra']),
        'reg': sum(1 for r in rows if r['reg']),
        'enabled': sum(1 for r in rows if r['enabled']),
        'native': sum(1 for r in rows if r['native']),
        'plan': sum(1 for r in rows if r['plan']),
        'gap': sum(1 for r in rows if not r['infra'] and not r['reg'] and not r['native']),
        'combos': sum(r['combos'] for r in rows if r['enabled']),
        'n_sl': n_sl,
        'n_tp': n_tp,
        'in_run': sum(1 for r in rows if r['rsym']),
        'ready': sum(1 for r in rows if r['rready']),
        'run_snap': run_snap,
    }
    return rows, stat


# ═══════════════════════════ РЕНДЕР ═══════════════════════════
def _cell(flag: bool, text: str = '✓', no: str = '—') -> str:
    if flag:
        return (f"<td style='text-align:center;color:{COL_GREEN_LT};"
                f"font-weight:700;'>{text}</td>")
    return f"<td style='text-align:center;color:{COL_MUTED};'>{no}</td>"


def _num(n: int) -> str:
    return f"{n:,}".replace(',', ' ')


def _stats_html(stat: dict) -> str:
    _KEEP = {'Standalone': 1, 'Finalized': 2, 'In plan': 3}  # порядок задаёт CSS order
    def cell(label, value, color=COL_TEXT, hint=''):
        if label not in _KEEP:
            return ''
        title = f" title='{hint}'" if hint else ''
        return (f"<div style='order:{_KEEP[label]};'><div class='lbl'{title}>{label}</div>"
                f"<div class='val' style='color:{color};'>{value}</div></div>")

    html = ["<div class='rdm-stats'>"]
    html.append(cell('Файлов .py', _num(stat['files']),
                     hint='Все .py в strategies/, включая инфраструктурные'))
    html.append(cell('Standalone', _num(stat['files'] - stat['infra']),
                     COL_GREEN_LT, 'Модули-стратегии (без base/_bt_core/_calc_cache/_registry)'))
    html.append(cell('В реестре', _num(stat['reg']), COL_BLUE,
                     'Есть запись в strategies/_registry.py → REGISTRY'))
    html.append(cell('В батче', _num(stat['enabled']), COL_GREEN_LT,
                     'Ключ в ENABLED_BATCH — участвует в ночном пересчёте'))
    html.append(cell('Native', _num(stat['native']), COL_AMBER,
                     'Импортируется из functions.py — родная сетка семейств'))
    html.append(cell('In plan', _num(stat['plan']), COL_TEXT,
                     'Тип встречается в journals/active_state.json'))
    html.append(cell('Finalized', _num(stat.get('in_run', 0)), COL_BLUE,
                     'Модуль есть в family_status последнего рэнкинга ' +
                     (stat.get('run_snap') or '—')))
    html.append(cell('Готовы торговать', _num(stat.get('ready', 0)), COL_GREEN_LT,
                     'ready_to_trade = 1 хотя бы на одном символе'))
    if stat['gap']:
        html.append(cell('Не подключено', _num(stat['gap']), COL_MUTED,
                         'Нет ни в реестре, ни в родной сетке'))
    html.append(cell('Σ комб./симв.', _num(stat['combos']),
                     hint=f"Только батч реестра: параметризации × {stat['n_sl']} SL × "
                          f"{stat['n_tp']} TP"))
    html.append("</div>")
    return ''.join(html)


def _run_cell(r: dict) -> str:
    """Колонка «Финализировано» — ФАКТ последнего рэнкинга, а не намерение из кода.

    Зелёная галочка — модуль есть в снимке последнего прогона (family_status),
    «—» — модуля там нет: в ночной рэнкинг он не попадал.
    Покрытие, число символов и ready_to_trade — в подсказке при наведении.
    """
    if not r['rsym']:
        return f"<td style='text-align:center;color:{COL_MUTED};'>—</td>"
    cov = r['rcov']
    ready = int(r['rready'])
    cov_txt = f"{cov:.0f}%" if cov is not None else '—'
    _full = (r['rpart'] > 0) and (cov is not None and cov >= 99.5)
    color = COL_GREEN_LT if _full else COL_AMBER
    txt = '✓' if _full else '!'
    if ready:  # ready уходит только в подсказку
        txt = '✓' if _full else '!  '
    tip = (f"посчитано {r['rcached']} из {r['rplanned']} ({cov_txt}); символов {r['rsym']}; "
           f"в рэнкинге {r['rpart']}; готовы торговать на {ready}")
    return (f"<td class='mono' style='text-align:center;color:{color};' "
            f"title='{tip}'>{txt}</td>")


def _row_html(r: dict) -> str:
    cls = 'inf' if r['infra'] else ''
    if r['infra']:
        tail = ("<td colspan='7' class='left' style='color:#6E7681;'>"
                "инфраструктура — не стратегия</td>")
        return (f"<tr class='{cls}'>"
                f"<td class='mono left'>{r['file']}</td>"
                f"{tail}</tr>")
    cells = [
        f"<td style='text-align:center;color:{COL_GREEN_LT};font-weight:700;'>✓</td>",
        f"<td class='mono left'>{r['file']}</td>",
        (f"<td class='mono left' style='color:{COL_TEXT};'>{r['calc']}</td>"
         if r['calc'] else f"<td class='mono left' style='color:{COL_MUTED};'>—</td>"),
        _cell(r['entry'] and r['exit']),
        _cell(r['bt']),
        (f"<td class='mono' style='text-align:center;color:{COL_BLUE};'>{r['key']}</td>"
         if r['reg'] else f"<td style='text-align:center;color:{COL_MUTED};'>—</td>"),
        _cell(r['enabled']),
        _run_cell(r),
        (f"<td class='mono' style='text-align:right;'>{_num(r['combos'])}</td>"
         if r['combos'] else f"<td style='text-align:right;color:{COL_MUTED};'>—</td>"),
        _cell(r['native']),
        (f"<td class='mono' style='text-align:center;color:{COL_AMBER};'>{r['fam']}</td>"
         if r['fam'] else f"<td style='text-align:center;color:{COL_MUTED};'>—</td>"),
        _cell(r['plan'], text='✓'),
        _cell(r['pos'], text='●'),
    ]
    # Видимые колонки: Модуль, Расчёт сигнала, Standalone, entry+exit, backtest,
    # type, Финализировано, В плане. Остальные ячейки считаются, но не рисуются.
    # (порядок ячеек собирается ниже, после _type)
    _type = (f"<td class='mono' style='text-align:center;color:{COL_AMBER};'>"
             f"{r['fam']}<span style='color:{COL_MUTED};font-size:0.72rem;'> native</span></td>"
             if r['native'] else
             f"<td class='mono' style='text-align:center;color:{COL_BLUE};'>"
             f"{r['key']}<span style='color:{COL_MUTED};font-size:0.72rem;'> реестр</span></td>"
             if r['reg'] else
             f"<td style='text-align:center;color:{COL_MUTED};'>—</td>")
    _cells = [cells[1], cells[2], _type, cells[0], cells[3], cells[4], cells[7], cells[11]]
    return f"<tr class='{cls}'>{''.join(_cells)}</tr>"


def render_roadmap_tab() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

    rows, stat = _scan()
    if not rows:
        st.warning(f"Папка strategies/ недоступна или пуста: `{STRAT_DIR}`")
        return  # не st.stop(): Roadmap рендерится раньше Backtest — stop убил бы и его

    st.markdown(_stats_html(stat), unsafe_allow_html=True)

    # ── Фильтры ──
    f1, f2, f3 = st.columns([2, 2, 2])
    with f1:
        query = st.text_input("Поиск по имени файла / ключу", '', key='rdm_q')
    with f2:
        view = st.selectbox(
            "Показать",
            ("Все", "Только пробелы (нет ни в реестре, ни в native)",
             "Только реестр", "Только батч", "Только native", "Только в плане",
             "Только готовые к торговле", "Только не финализированные"),
            key='rdm_view',
        )
    with f3:
        hide_infra = st.checkbox("Скрыть инфраструктуру", value=True, key='rdm_hide_infra')

    q = (query or '').strip().lower()
    shown = []
    for r in rows:
        if hide_infra and r['infra']:
            continue
        if q and q not in r['module'].lower() and q not in r['key'].lower():
            continue
        if view == 'Только пробелы (нет ни в реестре, ни в native)' and (r['reg'] or r['native']):
            continue
        if view == 'Только реестр' and not r['reg']:
            continue
        if view == 'Только батч' and not r['enabled']:
            continue
        if view == 'Только native' and not r['native']:
            continue
        if view == 'Только в плане' and not r['plan']:
            continue
        if view == 'Только готовые к торговле' and not r['rready']:
            continue
        if view == 'Только не финализированные' and r['rsym']:
            continue
            # дубль continue убран (фильтр выше)
        shown.append(r)

    if not shown:
        st.info("Под фильтр ничего не подошло.")
        return

    head = (
        "<table class='rdm'><thead><tr>"
        # Module · Signal calc · type · Standalone · entry+exit · backtest · Finalized · In plan
        "<th class='left'>Module</th>"
        "<th class='left' title='Signal calc: def calc_... inside the module'>Signal calc</th>"
        "<th title='Strategy Tree type: registry key or native family'>type</th>"
        "<th title='Module file exists in strategies/'>Standalone</th>"
        "<th>entry+exit</th>"
        "<th>backtest</th>"
        # type переехал сразу после Signal calc
        # (убрано: «Батч» — ключ ENABLED_BATCH виден в подсказке колонки type)
        "<th>Finalized</th>"
        # (убрано: «Комб./симв.» — неинформативно)
        # (убрано: native-слой показан прямо в колонке type)
        # (убрано: имя семейства показано в колонке type)
        "<th>In plan</th>"
        # (убрано: колонка «Позиция»)
        "</tr></thead><tbody>"
    )
    body = ''.join(_row_html(r) for r in shown)
    st.markdown(f"<div class='rdm-wrap'>{head}{body}</tbody></table></div>",
                unsafe_allow_html=True)
    _snap = stat.get('run_snap') or ''
    _snap_txt = f" от {_snap}" if _snap else " — БД журналов недоступна"
    st.caption(f"Показано {len(shown)} из {stat['files']} файлов. "
               f"Финализировано: family_status{_snap_txt}. "
               f"Кэш инвентаризации — 2 мин (обновится само после деплоя)."
               )

    with st.expander("Что означает каждая колонка", expanded=False):
        st.markdown(
            """
| Колонка | Откуда берётся | Что значит |
|---|---|---|
| **Standalone** | `os.listdir('strategies')` | Файл модуля существует. Зелёная галочка у всех — это отправная точка, а не «подключено». |
| **Модуль** | имя файла | `xxx.py` → модуль `strategies.xxx`. |
| **Расчёт сигнала** | регексп `^def calc_\\w+` в файле | Функция расчёта сигнальной колонки `k`. Есть — модуль живой, нет — заготовка. |
| **entry+exit** | `def check_entry` / `def check_exit` | Live-контракт реестра: без них реестр не может торговать модуль. |
| **backtest** | `def backtest` | Функция прогона для ночной сетки. |
| **type** | ключ реестра или ключ native-семейства | Имя стратегии в Strategy Tree: `adx native` или `triple_ema реестр`. Именно оно уходит в `type` результата и в категорию `SYMBOL_type`. |
| ~~Батч~~ | — | Колонка убрана: ключ в `ENABLED_BATCH` виден в подсказке колонки type. |
| **Финализировано** | `trades_db.family_status` (снимок после рэнкинга) | ✓ = модуль есть в снимке последнего прогона; `—` = в рэнкинг не попадал. Покрытие комбинаций, число символов и ready_to_trade — в подсказке. | 
| ~~Комб./симв.~~ | — | Колонка убрана как неинформативная: число заполнялось только у реестра. |
| ~~Native~~ | — | Колонка убрана: слой показан прямо в type (`native` серым). |
| ~~Семейство~~ | — | Колонка убрана: имя семейства показано в type. |
| **В плане** | `journals/active_state.json` | Тип встречается в текущем торговом плане. |
| ~~Позиция~~ | — | Колонка убрана (открытые позиции видно в Wheel и Daily Plan). |

Порядок строк: сначала родные семейства (native), затем реестр, затем кандидаты
без подключения. Инфраструктурные файлы (`base.py`, `_bt_core.py`, `_calc_cache.py`,
`_registry.py`, `__init__.py`) — в конце и серым: это не стратегии.
            """
        )
