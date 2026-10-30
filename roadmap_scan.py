"""Инвентаризация Roadmap БЕЗ streamlit — источник данных для SQL.

Раньше этот код жил внутри roadmap_tab.py и вызывался при каждом рендере вкладки:
читались 100+ файлов strategies/*.py и functions.py, всё парсилось регекспами.
Дашборд подвисал. Теперь:

  roadmap_scan.scan()      — считает строки (файлы + реестр + снимки из trades.db);
  roadmap_build.refresh()  — scan() + запись в SQL (roadmap_store);
  roadmap_tab              — только читает SQL (roadmap_store.load()).

Модуль намеренно не импортирует streamlit: его вызывает торговый цикл (main.py),
а он не должен тянуть веб-стек.

Слои (слева направо в таблице):
  Standalone   — файл модуля существует в strategies/            (✓ у всех)
  calc_*       — функция расчёта сигнала внутри модуля
  entry / exit — check_entry / check_exit (live-контракт реестра)
  backtest     — функция backtest(...) внутри модуля
  Реестр       — ключ в strategies/_registry.py → REGISTRY (--/ключ)
  Батч         — ключ в ENABLED_BATCH (участвует в ночном пересчёте)
  Native       — модуль импортируется из functions.py (родная сетка семейств)
  Семейство    — ключ семейства родной сетки (если удалось сопоставить)
  В плане      — тип есть в journals/active_state.json (торговый план)
  score        — family_score / family_status последнего прогона

Всё считается на месте (файлы + реестр + active_state.json), поэтому таблица
не расходится с кодом: добавили модуль — появилась строка с ✓ Standalone и
пустыми слоями ниже, и сразу видно, чего не хватает. Обновление — пересборкой
(кнопка «Пересчитать» в дэше или roadmap_build.refresh() из цикла).
"""

from __future__ import annotations

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
STRAT_DIR = os.path.join(HERE, 'strategies')
JOURNALS_DIR = os.path.join(HERE, 'journals')

# Файлы, которые не являются стратегиями: показываем внизу таблицы, чтобы
# ничего не «пропадало» из списка папки.
INFRA = {'__init__.py', 'base.py', '_bt_core.py', '_calc_cache.py', '_registry.py'}

_CALC_RE = re.compile(r"^def\s+(calc_\w+)\s*\(", re.M)


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


def scan():
    """Полная инвентаризация: (rows, stat). Без кэша — кэш теперь в SQL."""
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
