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
COL_RED = '#F85149'
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


def _family_scores():
    """score семейств из trades_db.family_score — по ВСЕМ посчитанным комбинациям.

    Зачем отдельно от family_status: там best_score считается по all_results,
    то есть по комбинациям, уже прошедшим дедуп и фильтры рэнкинга. Семейство,
    целиком оказавшееся ниже порога, оставалось вообще без оценки — в таблице
    был прочерк. family_score пишется из чекпойнтов символов, где лежат ВСЕ
    комбинации, поэтому оценка есть всегда: даже отрицательная и даже ниже
    min_score. Такие строки и красим красным.

    Возвращает dict: family -> {'score': среднее best_score по символам,
    'max': лучший символ, 'min': порог отбора, 'combos', 'positive',
    'syms': set(), 'snap': время записи}. Нет таблицы — пустой dict, и тогда
    работает прежний источник (family_status).
    """
    out = {}
    try:
        import trades_db as _tdb
        con = _tdb.connect(readonly=True)
    except Exception:
        return out
    try:
        if not {x[1] for x in con.execute("PRAGMA table_info(family_score)")}:
            return out          # старая БД: таблицы ещё нет — работаем по family_status
        for r in con.execute(
                "SELECT family, symbol, best_score, min_score, n_combos, n_positive, "
                "snapshot_at FROM family_score"):
            fam = str(r['family'] or '')
            if not fam:
                continue
            f = out.setdefault(fam, {'scores': [], 'mins': [], 'combos': 0,
                                     'positive': 0, 'syms': set(), 'snap': ''})
            try:
                f['scores'].append(float(r['best_score'] or 0.0))
            except (TypeError, ValueError):
                pass
            try:
                _m = float(r['min_score'] or 0.0)
                if _m > 0:
                    f['mins'].append(_m)
            except (TypeError, ValueError):
                pass
            f['combos'] += int(r['n_combos'] or 0)
            f['positive'] += int(r['n_positive'] or 0)
            if r['symbol']:
                f['syms'].add(str(r['symbol']))
            f['snap'] = str(r['snapshot_at'] or f['snap'])
    except Exception:
        return out
    finally:
        try:
            con.close()
        except Exception:
            pass
    for f in out.values():
        _sc = f.pop('scores')
        f['score'] = (sum(_sc) / len(_sc)) if _sc else None
        f['max'] = max(_sc) if _sc else None
        _mn = f.pop('mins')
        f['min'] = max(_mn) if _mn else None
    return out


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
        # Колонки новой базы читаем по факту: если в развёрнутой БД снимок старше
        # (нет n_ranked/n_active) — подставляем NULL, а не теряем весь снимок.
        _have = {x[1] for x in con.execute("PRAGMA table_info(family_status)")}

        def _c(name):
            return name if name in _have else f"NULL AS {name}"

        for r in con.execute(
                "SELECT family, label, combos_planned, combos_cached, "
                + ", ".join(_c(_n) for _n in (
                    "participates", "ready_to_trade", "snapshot_at", "best_score",
                    "min_score", "run_kind", "symbol", "n_ranked", "n_active"))
                + " FROM family_status"):

            fam = str(r['family'] or '')
            if not fam:
                continue
            f = facts.setdefault(fam, {
                'family': fam, 'label': str(r['label'] or ''),
                'planned': 0, 'cached': 0, 'symbols': 0, 'ready': 0, 'part': 0,
                # score последнего рэнкинга: best_score по каждому символу семейства,
                # порог min_score прогона, вид прогона (full/incremental/...) и символы —
                # нужны для колонки «score» и её цвета (свежесть бэктеста).
                'scores': [], 'mins': [], 'kinds': set(), 'syms': set(),
                # n_ranked/n_active — чтобы честно сказать, ПОЧЕМУ score нет:
                # строка есть, но ни одна комбинация не прошла фильтры рэнкинга.
                'ranked': 0, 'active': 0,
            })
            f['symbols'] += 1
            f['planned'] += int(r['combos_planned'] or 0)
            f['cached'] += int(r['combos_cached'] or 0)
            f['ranked'] += int(r['n_ranked'] or 0)
            f['active'] += int(r['n_active'] or 0)
            f['ready'] += 1 if r['ready_to_trade'] else 0
            f['part'] += 1 if r['participates'] else 0
            try:
                _bs = float(r['best_score'] or 0.0)
            except (TypeError, ValueError):
                _bs = 0.0
            if _bs > 0:                      # 0 = score не считался (старая строка)
                f['scores'].append(_bs)
            try:
                _ms = float(r['min_score'] or 0.0)
            except (TypeError, ValueError):
                _ms = 0.0
            if _ms > 0:
                f['mins'].append(_ms)
            if r['run_kind']:
                f['kinds'].add(str(r['run_kind']))
            if r['symbol']:
                f['syms'].add(str(r['symbol']))
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
    _fscores = _family_scores()   # score по ВСЕМ комбинациям (включая ниже порога)
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

        # ── score семейства на последнем рэнкинге ─────────────────────────────
        # Стратегия в плане атомарна, а строка таблицы — семейство (модуль).
        # Агрегация: среднее best_score по символам семейства (best_score каждой
        # строки family_status — ЛУЧШАЯ комбинация семейства на этом символе).
        # Цвет — «дата скоринга == дата бэктеста»:
        #   зелёный — комбинации семейства посчитаны ПОЛНОСТЬЮ в последнем
        #             прогоне (покрытие ≥ 99.5%): score стоит на свежих данных;
        #   жёлтый  — покрытие < 100%: часть комбинаций из кэша, т.е. бэктест
        #             семейства старше даты скоринга;

        #   «—»     — score нет (семейства нет в снимке либо n_ranked = 0).
        # run_kind НЕ гейт: рутина идёт incremental/incomplete, и на нём столбец
        # был бы жёлтым даже при 100% покрытии комбинаций.
        _rscore, _rmin, _rkinds, _rsyms = [], [], set(), set()
        _rranked = _ractive = 0
        for _fk in _rkeys:
            _rf = run_facts[_fk]
            _rscore += list(_rf.get('scores') or [])
            _rmin += list(_rf.get('mins') or [])
            _rkinds |= set(_rf.get('kinds') or ())
            _rsyms |= set(_rf.get('syms') or ())
            _rranked += int(_rf.get('ranked') or 0)
            _ractive += int(_rf.get('active') or 0)
        _score_mean = (sum(_rscore) / len(_rscore)) if _rscore else None
        _score_max = max(_rscore) if _rscore else None
        _min_score = max(_rmin) if _rmin else None
        # score из family_score (все комбинации) приоритетнее family_status:
        # там оценка есть и у семейства, целиком оказавшегося ниже порога.
        _fs = [_fscores[k] for k in _rkeys
               if k in _fscores and _fscores[k].get('score') is not None]
        if _fs:
            _score_mean = sum(x['score'] for x in _fs) / len(_fs)
            _score_max = max((x['max'] for x in _fs if x['max'] is not None), default=None)
            _fs_min = max((x['min'] for x in _fs if x['min'] is not None), default=None)
            if _fs_min is not None:
                _min_score = _fs_min
            _score_src = 'family_score'
            _score_combos = sum(x['combos'] for x in _fs)
            _score_pos = sum(x['positive'] for x in _fs)
        else:
            _score_src = 'family_status'
            _score = _score_mean
            _score_combos = None
            _score_pos = None
        # ── score колонки = МАКСИМУМ по символам (чемпион семейства) ──
        # План (distribute_lots) берёт ЛУЧШУЮ комбинацию семейства на КОНКРЕТНОМ
        # символе, а не среднее по всем. Поэтому и в таблице показываем максимум:
        # иначе строка «в плане» со score 0.35 при пороге 1.0 выглядела как ошибка,
        # хотя её чемпион на другом символе порог прошёл. Среднее — в подсказке.
        if _score_max is not None:
            _score = _score_max
        _score_fresh = bool(_score is not None
                            and _rcov is not None and _rcov >= 99.5)
        # Прозрачная причина пустого score — уходит в подсказку курсором.
        if _score is not None:
            _score_reason = ''
        elif not _rkeys:
            _score_reason = ('нет строки в family_status: семейство не попало в план '
                             'последнего прогона')
        elif _rranked <= 0:
            _score_reason = ('score не считался: ни одна комбинация семейства не '
                             'прошла фильтры рэнкинга (n_ranked = 0)')
        else:
            _score_reason = f'score пустой при n_ranked = {_rranked}'
        # Состояние score для цвета ячейки:
        #   red   — бэктест ЕСТЬ, но комбинации не прошли порог отбора: либо
        #           ни одна (n_ranked = 0 → в базе best_score = 0), либо
        #           лучший score ниже min_score прогона. Такие строки —
        #           «стратегия посчитана, но ниже фильтров», их видно красным.
        #   green — score выше порога и покрытие полное (score = свежий бэктест);
        #   amber — score выше порога, но покрытие < 100% (часть из кэша);
        #   none  — score нет вовсе (не бэктестилось / нет снимка).
        if _score is not None and _min_score is not None and _score < _min_score:
            _score_state = 'red'
        elif _score is not None:
            _score_state = 'green' if _score_fresh else 'amber'
        elif _rkeys and _rplanned > 0 and _rcached > 0 and _rranked <= 0:
            _score_state = 'red'   # посчитано, но всё отфильтровано порогами
        else:
            _score_state = 'none'
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
            'score': _score,                        # МАКСИМУМ best_score по символам (чемпион)
            'score_max': _score_max,
            'score_mean': _score_mean,              # среднее по символам (только подсказка)
            'min_score': _min_score,
            'score_fresh': _score_fresh,
            'score_state': _score_state,
            'score_src': _score_src,        # family_score (все комбинации) | family_status
            'score_combos': _score_combos,  # сколько комбинаций посчитано
            'score_pos': _score_pos,        # сколько из них со score > 0
            'run_kinds': sorted(_rkinds),
            'score_syms': len(_rsyms),
            'score_reason': _score_reason,
            'n_ranked': _rranked,
            'n_active': _ractive,
            'bytes': len(src),
        })

    # Порядок: родные → реестр → кандидаты; инфраструктура всегда в конце.
    def _ord(r):
        tier = 0 if r['native'] else (1 if r['reg'] else 2)
        return (1 if r['infra'] else 0, tier, r['module'])

    rows.sort(key=_ord)

    # Какие виды прогона вообще писались в снимок (для подписи под таблицей):
    # в рутине это обычно none/incomplete — поэтому run_kind не гейт для цвета.
    _all_kinds = sorted({k for _f in run_facts.values()
                         for k in (_f.get('kinds') or ())})

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
        'run_kinds': _all_kinds,
        'n_score': sum(1 for r in rows if r['score'] is not None),
    }
    return rows, stat


# ═══════════════════════════ Р Р•РќР”Р•Р  ═══════════════════════════
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


def _score_cell(r: dict) -> str:
    """Колонка «score» — оценка семейства: family_score (все комбинации) → family_status.

    Строка таблицы — семейство (модуль), а score в базе считается на пару
    (symbol, family): показываем МАКСИМУМ best_score по символам (чемпион),
    именно он решает допуск в план; среднее и порог прогона — в подсказке.

    Цвет — соответствие скоринга дате бэктеста:
      зелёный — комбинации семейства посчитаны ПОЛНОСТЬЮ в последнем прогоне
                (покрытие ≥ 99.5%): score и бэктест из одного прогона;
      жёлтый  — покрытие < 100%: часть комбинаций взята из кэша, т.е. данные
                бэктеста старше даты скоринга;
      красный — score ниже порога min_score: посчитано, но отбор не прошло;
      «—»     — комбинаций нет вовсе (семейство не бэктестилось).
    """
    sc = r.get('score')
    _state = r.get('score_state') or ('none' if sc is None else 'amber')
    if _state == 'red' and sc is None:
        sc = 0.0   # посчитано, но ни одна комбинация не прошла порог → score 0
    if sc is None:
        _why = r.get('score_reason') or 'score не считался'
        return (f"<td style='text-align:center;color:{COL_MUTED};' "
                f"title='{_why}'>—</td>")

    _state_colors = {'green': COL_GREEN_LT, 'amber': COL_AMBER, 'red': COL_RED}
    color = _state_colors.get(_state, COL_AMBER)
    _kinds = ', '.join(r.get('run_kinds') or []) or '—'
    _min_s = r.get('min_score')
    _min_txt = f"{_min_s:.2f}" if isinstance(_min_s, (int, float)) else '—'
    _mean_s = r.get('score_mean')
    _mean_txt = f"{_mean_s:.2f}" if isinstance(_mean_s, (int, float)) else '—'
    cov = r.get('rcov')
    tip = (f"score {sc:.2f} — лучший из {r.get('score_syms', 0)} символов (чемпион: "
           f"по нему и допуск в план); среднее по символам {_mean_txt}; порог {_min_txt}; "
           f"прогон {_kinds}; покрытие "
           + (f"{cov:.0f}%" if cov is not None else '—')
           + ("; покрытие полное — бэктест свежий" if r.get('score_fresh')
              else "; покрытие < 100% — часть комбинаций из кэша"))
    if r.get('plan'):
        if _state == 'red':
            tip += '; в плане: да, но score ниже порога (план из другого прогона)'
        else:
            tip += '; в плане: да — чемпион семейства прошёл порог'
    if _state == 'red':
        tip += ('; НИЖЕ ПОРОГА: ни на одном символе лучшая комбинация не дотянула '
                'до min_score — '
                + (r.get('score_reason') or 'лучший score ниже min_score'))
    return (f"<td class='mono' style='text-align:center;color:{color};' "
            f"title='{tip}'>{sc:.2f}</td>")


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
        tail = ("<td colspan='8' class='left' style='color:#6E7681;'>"
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
        _score_cell(r),
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
    # type — «стратегия в плане»: native-семейство либо ключ реестра.
    # type-ячейка нужна ниже: склеиваем видимый порядок колонок после её сборки.

    _type = (f"<td class='mono' style='text-align:center;color:{COL_AMBER};'>"
             f"{r['fam']}<span style='color:{COL_MUTED};font-size:0.72rem;'> native</span></td>"
             if r['native'] else
             f"<td class='mono' style='text-align:center;color:{COL_BLUE};'>"
             f"{r['key']}<span style='color:{COL_MUTED};font-size:0.72rem;'> реестр</span></td>"
             if r['reg'] else
             f"<td style='text-align:center;color:{COL_MUTED};'>—</td>")
    # Видимые колонки: Модуль · Расчёт сигнала · type · score · Standalone ·
    # backtest · score · Финализировано · В плане. Остальные ячейки (ключ реестра,
    # батч, комбинации, native, семейство, позиция) считаются, но не рисуются.
    _cells = [cells[1], cells[2], _type, cells[5], cells[0], cells[3], cells[4],
              cells[8], cells[12]]
    return f"<tr class='{cls}'>{''.join(_cells)}</tr>"


def _plan_gates() -> dict:
    """Пороги отбора в торговый план из config.py (с безопасными дефолтами).

    Значения читаются на лету: если конфиг поменяли, подпись внизу таблицы
    показывает актуальные пороги, а не зашитые в текст числа.
    """
    g = {'min_score': 1.0, 'min_trades': 10, 'min_tstat': 2.5, 'rr': 0.5,
         'payoff': 0.6, 'min_lot': 0.01, 'plan_max': 40, 'max_per_type': 8}
    try:
        from config import RiskParams, BacktestConfig, MIN_TP_SL_RATIO, MIN_PAYOFF
        _rp, _bt = RiskParams(), BacktestConfig()
        g['min_score'] = float(getattr(_rp, 'min_score', g['min_score']))
        g['min_tstat'] = float(getattr(_rp, 'min_tstat', g['min_tstat']))
        g['min_lot'] = float(getattr(_rp, 'min_lot', g['min_lot']))
        g['plan_max'] = int(getattr(_rp, 'plan_max_strategies', g['plan_max']))
        g['max_per_type'] = int(getattr(_rp, 'max_per_type', g['max_per_type']))
        g['min_trades'] = int(getattr(_bt, 'min_trades_rank', g['min_trades']))
        g['rr'] = float(MIN_TP_SL_RATIO)
        g['payoff'] = float(MIN_PAYOFF)
    except Exception:
        pass
    return g


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
        only_below = st.checkbox("Только ниже порога (score < min_score)",
                                value=False, key='rdm_below')

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
        if only_below and r.get('score_state') != 'red':
            continue   # «ниже порога»: посчитано, но комбинации отфильтрованы
        shown.append(r)

    if not shown:
        st.info("Под фильтр ничего не подошло.")
        return

    head = (
        "<table class='rdm'><thead><tr>"
        # Порядок: Module · Signal calc · type · score · Standalone · entry+exit ·
        # backtest · Finalized · In plan
        "<th class='left'>Module</th>"
        "<th class='left' title='Signal calc: def calc_... inside the module'>Signal calc</th>"
        "<th title='Strategy Tree type: registry key or native family'>type</th>"
        "<th title='Score семейства: МАКСИМУМ best_score по посчитанным "
        "комбинациям (family_score) — чемпион, по нему и допуск в план. "
        "Зелёный — выше порога и покрытие полное; жёлтый — часть комбинаций "
        "из кэша; красный — даже лучший символ ниже порога min_score'>score</th>"
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
    _n_score = sum(1 for r in shown if r.get('score') is not None)
    _n_red = sum(1 for r in shown if r.get('score_state') == 'red')
    st.caption(f"score: красным — {_n_red} строк, где ДАЖЕ лучший символ ниже "
               f"порога min_score (бэктест есть, отбор не прошло). В колонке — максимум "
               f"по символам (лучшая посчитанная комбинация, до фильтров рэнкинга). Среднее — в подсказке. "
               f"Зелёный — покрытие полное, жёлтый — часть комбинаций из кэша.")
    _snap_txt = f" от {_snap}" if _snap else " — БД журналов недоступна"
    st.caption(f"Показано {len(shown)} из {stat['files']} файлов. "
               f"Финализировано: family_status{_snap_txt}. "
               f"score: зелёный — комбинации посчитаны полностью; жёлтый — часть из "
               f"кэша. Есть у {_n_score} из {len(shown)} строк (причина «—» — в "
               f"подсказке курсором). "
               f"Вид последнего прогона: "
               f"{', '.join(stat.get('run_kinds') or []) or '—'}. "

               f"Кэш инвентаризации — 2 мин (обновится само после деплоя)."
               )

    _pg = _plan_gates()
    st.caption(
        "Что попадает в план: дедуп по param_key → "
        f"score ≥ {_pg['min_score']:.2f} → сделок ≥ {_pg['min_trades']} → "
        f"t-стат ≥ {_pg['min_tstat']:.1f} (либо чемпион семейства) → "
        f"TP ≥ {_pg['rr']:.2f}·SL и payoff ≥ {_pg['payoff']:.2f} → "
        f"лот ≥ {_pg['min_lot']:.2f} после квоты и капов → "
        f"слотов ≤ {_pg['plan_max']}, на один тип ≤ {_pg['max_per_type']}. "
        "score выше порога — необходимое, но не достаточное условие: если тип уже занял "
        f"{_pg['max_per_type']} слотов, следующие его комбинации в план не попадут, "
        "каким бы ни был score."
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
| **score** | `trades_db.family_score` → `family_status` (`best_score` последнего рэнкинга) | Оценка семейства: МАКСИМУМ `best_score` по символам, где семейство участвует (в базе score считается на пару symbol+family — это лучшая комбинация семейства на символе; в колонке — максимум по символам, т.е. тот же критерий отбора, по которому план берёт чемпиона). В подсказке: среднее по символам, порог `min_score`, вид прогона, покрытие. **Зелёный** = комбинации семейства посчитаны полностью в последнем прогоне (покрытие ≥ 99.5%) — score и бэктест из одного прогона; **жёлтый** = покрытие < 100%, часть комбинаций взята из кэша (бэктест старше скоринга); **«—»** = комбинаций нет вовсе (семейство не бэктестилось); **красный** = даже лучший символ ниже порога `min_score` (видно число). Приоритет источников — в строке «score: источник» ниже. |
| **Финализировано** | `trades_db.family_status` (снимок после рэнкинга) | ✓ = модуль есть в снимке последнего прогона; `—` = в рэнкинге не участвовал. Покрытие комбинаций, число символов и `ready_to_trade` — в подсказке. |
| **score: источник** | `trades_db.family_score` (считается из чекпойнтов) | Лучший `score` среди ВСЕХ посчитанных комбинаций семейства на каждом символе — до дедупа и фильтров рэнкинга. В колонке `score` показывается МАКСИМУМ этих значений по символам (чемпион семейства — именно он решает допуск в план), среднее по символам — в подсказке. Поэтому оценка есть и у семейства, целиком оказавшегося ниже порога: **красный** = score < `min_score` (посчитано, но отбор не прошло), значение показано числом, а не прочерком. Если таблицы/строк нет — используется `family_status.best_score` (тогда оценка только у прошедших фильтры). |
| ~~Комб./симв.~~ | — | Колонка убрана как неинформативная: число заполнялось только у реестра. |
| ~~Native~~ | — | Колонка убрана: слой показан прямо в type (`native` серым). |
| ~~Семейство~~ | — | Колонка убрана: имя семейства показано в type. |
| **В плане** | `journals/active_state.json` | Тип встречается в текущем торговом плане. |
| ~~Позиция~~ | — | Колонка убрана (открытые позиции видно в Wheel и Daily Plan). |

Порядок строк: сначала родные семейства (native), затем реестр, затем кандидаты без
подключения. Инфраструктурные файлы (`base.py`, `_bt_core.py`, `_calc_cache.py`,
`_registry.py`, `__init__.py`) — в конце и по умолчанию скрыты.

Чекбокс «Только ниже порога» оставляет строки с красным score: бэктест есть, но ни одна
комбинация не прошла `min_trades` / `min_score` / t-stat. То есть стратегия посчитана и
плохая по цифрам — а не отсутствует.
"""
        )
