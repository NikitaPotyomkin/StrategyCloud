"""Хранилище таблицы Roadmap в SQL (journals/trades.db).

Зачем: раньше вкладка Roadmap строилась в дашборде — на каждый рендер читались
100+ файлов strategies/*.py плюс functions.py и парсились регекспами, из-за чего
дэш подвисал. Теперь инвентаризация считается ОДИН раз (roadmap_build.refresh(),
вызывается из торгового цикла), лежит в этих таблицах, а вкладка просто читает.

Таблицы (отдельные, схему trades_db не трогаем):
  roadmap_rows  — одна строка на модуль strategies/*.py. Полный набор полей
                  таблицы лежит в payload (JSON), а в обычных колонках — только
                  то, по чему удобно фильтровать/сортировать в SQL.
  roadmap_meta  — одна строка (id=1): время сборки и сводка stat (JSON).

Почему payload, а не 35 колонок: набор полей таблицы меняется чаще, чем схема
БД, — новая колонка в дэше не требует миграции. Колонки-дубли (module, score,
score_state, reg, native, in_plan, ready) заполняются для запросов руками.

Порядок строк сохраняется: строки вставляются в порядке, который задал
roadmap_scan.scan() (native → реестр → кандидаты, инфраструктура в конце),
а читаются по rowid.
"""

from __future__ import annotations

import datetime
import json

import trades_db as _tdb

_SQL = """
CREATE TABLE IF NOT EXISTS roadmap_rows (
    module      TEXT PRIMARY KEY,
    file        TEXT,
    saved_at    TEXT,
    reg         INTEGER,
    native      INTEGER,
    in_plan     INTEGER,
    ready       INTEGER,
    score       REAL,
    score_state TEXT,
    payload     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_roadmap_rows_score ON roadmap_rows(score);
CREATE INDEX IF NOT EXISTS ix_roadmap_rows_state ON roadmap_rows(score_state);

CREATE TABLE IF NOT EXISTS roadmap_meta (
    id       INTEGER PRIMARY KEY CHECK (id = 1),
    saved_at TEXT,
    n_rows   INTEGER,
    stat     TEXT
);
"""


def ensure(con) -> None:
    """Создать таблицы, если их ещё нет."""
    con.executescript(_SQL)


def _js(obj):
    """Запасная сериализация для set/кортежей и прочих нестандартных типов."""
    if isinstance(obj, (set, frozenset, tuple)):
        return list(obj)
    return str(obj)


def save(rows, stat, path=None, verbose: bool = False) -> int:
    """Полностью заменить содержимое таблиц. Возвращает число записанных строк."""
    saved_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    con = _tdb.connect(path)
    try:
        ensure(con)
        ent = []
        for r in rows or []:
            _key = str(r.get('module') or r.get('file') or '')
            if not _key:
                continue
            try:
                _payload = json.dumps(r, ensure_ascii=False, default=_js)
            except (TypeError, ValueError):
                continue
            _score = r.get('score')
            ent.append((
                _key,
                str(r.get('file') or ''),
                saved_at,
                1 if r.get('reg') else 0,
                1 if r.get('native') else 0,
                1 if r.get('plan') else 0,
                1 if r.get('rready') else 0,
                (float(_score) if _score is not None else None),
                str(r.get('score_state') or ''),
                _payload,
            ))
        con.execute("DELETE FROM roadmap_rows")
        con.executemany(
            "INSERT OR REPLACE INTO roadmap_rows (module, file, saved_at, reg, native, "
            "in_plan, ready, score, score_state, payload) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)", ent)
        con.execute(
            "INSERT OR REPLACE INTO roadmap_meta (id, saved_at, n_rows, stat) "
            "VALUES (1, ?, ?, ?)",
            (saved_at, len(ent),
             json.dumps(stat or {}, ensure_ascii=False, default=_js)))
        con.commit()
        if verbose:
            print(f"  [ROADMAP] записано {len(ent)} строк ({saved_at})", flush=True)
        return len(ent)
    finally:
        try:
            con.close()
        except Exception:
            pass


def load(path=None):
    """Прочитать таблицу: (rows, stat, saved_at). Пусто — ([], {}, '')."""
    try:
        con = _tdb.connect(path, readonly=True)
    except Exception:
        return [], {}, ''
    try:
        rows = []
        for r in con.execute("SELECT payload FROM roadmap_rows ORDER BY rowid"):
            try:
                rows.append(json.loads(r['payload']))
            except (TypeError, ValueError):
                continue
        stat, saved_at = {}, ''
        try:
            meta = con.execute(
                "SELECT saved_at, stat FROM roadmap_meta WHERE id = 1").fetchone()
        except Exception:
            meta = None
        if meta is not None:
            saved_at = str(meta['saved_at'] or '')
            try:
                stat = json.loads(meta['stat'] or '{}') or {}
            except (TypeError, ValueError, json.JSONDecodeError):
                stat = {}
        return rows, stat, saved_at
    except Exception:
        return [], {}, ''
    finally:
        try:
            con.close()
        except Exception:
            pass


def age_sec(path=None):
    """Сколько секунд назад собиралась таблица (None — записи нет)."""
    _rows, _stat, saved_at = load(path)
    if not saved_at:
        return None
    try:
        t = datetime.datetime.strptime(saved_at, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None
    return max(0.0, (datetime.datetime.now() - t).total_seconds())
