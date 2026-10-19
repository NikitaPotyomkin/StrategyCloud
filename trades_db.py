"""История сделок в SQLite (шаг 1: запись; чтение — локальное).

Назначение:
    Постоянный «журнал сделок» в одном файле, богаче CSV: каждая строка — один
    MT5-deal со всеми полями (magic, тип/семейство стратегии, param_key,
    strategy_id, symbol, P&L, комиссия, своп, время, аккаунт).

Где лежит БД:
    journals/trades.db  (рядом с остальными journals — приезжает при копировании
    папки на другой стенд). Путь можно переопределить переменной окружения
    TRADES_DB_PATH — этим же ключом позже переключим на сетевую папку (шаг 2).

ВАЖНО про источник:
    MT5-история привязана к АККАУНТУ терминала. Поэтому наполнять БД нужно на
    том стенде, чьи сделки нужны (прод), а затем копировать файл/папку. На деве
    ту же БД открываем ТОЛЬКО на чтение (connect(readonly=True)).

Идемпотентность:
    Ключ — deal_ticket (PRIMARY KEY). Повторный ingest делает UPSERT, дублей нет.
    Можно спокойно перезапускать и «догонять» окно (overlap по времени).

Устойчивость:
    Все публичные функции глотают ошибки и возвращают 0/False — модуль никогда не
    должен ронять пайплайн. mt5 импортируется защищённо (для чтения БД на стенде
    без подключённого терминала).

CLI:
    python trades_db.py ingest [--days N] [--db PATH]   # добрать историю из MT5
    python trades_db.py stats  [--db PATH]              # сводка по БД
    python trades_db.py vacuum [--out PATH] [--db PATH] # консистентный снапшот файла
"""
import argparse
import csv
import datetime
import os
import sqlite3

try:  # чтение БД не требует терминала — импорт не должен падать
    import MetaTrader5 as mt5
except Exception:  # pragma: no cover
    mt5 = None

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_DB = os.path.join(_BASE_DIR, 'journals', 'trades.db')

# Диапазон пула magic наших стратегий (см. strategy_engine.make_magic/assign_magic)
MAGIC_POOL_LO = 770000
MAGIC_POOL_HI = 869999

# DEAL_ENTRY_* (числа фиксированы в MT5 API; не тянем mt5, чтобы читать БД без терминала)
_ENTRY_IN, _ENTRY_OUT, _ENTRY_INOUT = 0, 1, 2


def db_path(path=None):
    """Путь к БД: аргумент → TRADES_DB_PATH → journals/trades.db."""
    return path or os.environ.get('TRADES_DB_PATH') or _DEFAULT_DB


def _safe_int(value, default=0):
    """int() без исключений: мусор в CSV не должен ронять разбор реестра."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _registry_path():
    return os.path.join(_BASE_DIR, 'journals', 'strategy_registry.csv')


def connect(path=None, readonly=False):
    """Открыть БД. readonly=True — только чтение (для дева/сетевой папки)."""
    p = db_path(path)
    if readonly:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    else:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        con = sqlite3.connect(p)
        # DELETE (не WAL): один самодостаточный файл — безопасно копировать/шарить.
        con.execute('PRAGMA journal_mode=DELETE')
        con.execute('PRAGMA synchronous=NORMAL')
    con.row_factory = sqlite3.Row
    return con


def _table_exists(con, name):
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,)).fetchone()
    return row is not None


def ensure_schema(con):
    """Создать таблицы/индексы, если их нет (идемпотентно)."""
    con.executescript("""
    CREATE TABLE IF NOT EXISTS deals (
        deal_ticket      INTEGER PRIMARY KEY,   -- MT5 deal ticket (ключ идемпотентности)
        order_ticket     INTEGER,
        position_id      INTEGER,
        symbol           TEXT,
        magic            INTEGER,
        family           TEXT,   -- системное семейство (= тип стратегии, как в штурвале)
        label            TEXT,   -- короткое человекочитаемое имя из реестра (может быть NULL)
        param_key        TEXT,   -- параметр стратегии; ВСЕГДА текстом (int/str-грабли реестра)
        strategy_id      TEXT,   -- symbol_family_param_key — уникальный id стратегии
        category         TEXT,   -- symbol_family — sid категории штурвала
        entry            INTEGER,  -- 0=IN, 1=OUT, 2=INOUT
        deal_type        INTEGER,  -- 0=BUY, 1=SELL, ...
        volume           REAL,
        price            REAL,
        profit           REAL,
        commission       REAL,
        swap             REAL,
        fee              REAL,
        comment          TEXT,
        time             INTEGER,  -- серверное время сделки (unix, как в MT5)
        time_msc         INTEGER,
        account_login    INTEGER,
        account_server   TEXT,
        account_currency TEXT,
        is_ours          INTEGER,  -- 1 если magic в пуле [770000..869999]
        link_status      TEXT,     -- 'linked' (magic есть в реестре) / 'unlinked'
        ingested_at      TEXT      -- локальное время записи строки
    );
    CREATE INDEX IF NOT EXISTS ix_deals_position ON deals(position_id);
    CREATE INDEX IF NOT EXISTS ix_deals_magic    ON deals(magic);
    CREATE INDEX IF NOT EXISTS ix_deals_time     ON deals(time);
    CREATE INDEX IF NOT EXISTS ix_deals_category ON deals(category);
    CREATE INDEX IF NOT EXISTS ix_deals_symbol   ON deals(symbol);

    -- Снимок реестра на момент ингеста: magic → стратегия (magic переиспользуется
    -- во времени, поэтому история важна для аудита задним числом).
    CREATE TABLE IF NOT EXISTS registry_snapshot (
        magic          INTEGER,
        symbol         TEXT,
        type           TEXT,
        param_key      TEXT,
        label          TEXT,
        activated_at   TEXT,
        deactivated_at TEXT,
        conflict       INTEGER,
        snapshot_at    TEXT,
        PRIMARY KEY (magic, symbol, snapshot_at)
    );

    -- ── Пики нереализованной прибыли (шаг 1b) ──────────────────────────────
    -- equity_samples: 1 строка на тик семплера — общий floating счёта во времени.
    CREATE TABLE IF NOT EXISTS equity_samples (
        ts             INTEGER,  -- unix-время сэмпла
        account_login  INTEGER,
        balance        REAL,
        equity         REAL,
        floating_total REAL,     -- Σ(profit+swap) по всем открытым позициям
        n_positions    INTEGER
    );
    CREATE INDEX IF NOT EXISTS ix_equity_ts ON equity_samples(ts);
    CREATE INDEX IF NOT EXISTS ix_equity_login_ts ON equity_samples(account_login, ts);

    -- daily_peak: 1 строка на (день, аккаунт, категория) — экстремумы floating.
    -- UPSERT через MAX(peak_*) / MIN(min_*): храним ЛУЧШУЮ и ХУДШУЮ точку дня.
    CREATE TABLE IF NOT EXISTS daily_peak (
        day            TEXT,     -- 'YYYY-MM-DD'
        account_login  INTEGER,
        category       TEXT,     -- symbol_family (sid штурвала)
        peak_float     REAL,     -- макс. нереализованный floating по категории
        peak_ts        INTEGER,
        peak_volume    REAL,     -- суммарный объём в момент пика
        peak_per_lot   REAL,     -- peak_float / peak_volume (удельная)
        min_float      REAL,     -- мин. floating (просадка) по категории
        min_ts         INTEGER,
        realized_net   REAL,     -- реализовано за день по категории (из deals)
        samples        INTEGER,  -- сколько раз сэмплировали
        PRIMARY KEY (day, account_login, category)
    );
    CREATE INDEX IF NOT EXISTS ix_peak_day ON daily_peak(day);

    -- Одна строка состояния ингеста.
    CREATE TABLE IF NOT EXISTS ingest_log (
        id         INTEGER PRIMARY KEY CHECK (id = 1),
        last_time  INTEGER,  -- максимальный deal.time после последнего ingest
        last_run   TEXT,
        rows_total INTEGER
    );
    """)
    con.commit()


def load_registry():
    """magic → запись реестра (symbol, type, param_key, label, activated_at …)."""
    path = _registry_path()
    reg = {}
    if not os.path.exists(path):
        return reg
    try:
        from strategies._registry import label_for  # человекочитаемое имя (если доступно)
    except Exception:
        label_for = None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                try:
                    magic = int(row['magic'])
                except (TypeError, ValueError, KeyError):
                    continue
                stype = (row.get('type') or '').strip()
                reg[magic] = {
                    'symbol': (row.get('symbol') or '').strip(),
                    'family': stype,
                    'param_key': (row.get('param_key') or '').strip(),
                    'label': (label_for(stype) if label_for else None),
                    'activated_at': row.get('activated_at', ''),
                    'deactivated_at': row.get('deactivated_at', ''),
                    'conflict': _safe_int(row.get('conflict')),
                }
    except Exception:
        pass
    return reg


def _link_fields(deal, registry):
    """Резолв magic → (family, label, param_key, strategy_id, category, link_status)."""
    magic = int(getattr(deal, 'magic', 0) or 0)
    symbol = getattr(deal, 'symbol', '') or ''
    rec = registry.get(magic)
    if rec:
        family = rec['family']
        label = rec['label']
        param_key = rec['param_key']
        link_status = 'linked'
    else:
        family = label = param_key = None
        link_status = 'unlinked'
    strategy_id = f"{symbol}_{family}_{param_key}" if family else None
    category = f"{symbol}_{family}" if family else None
    return family, label, param_key, strategy_id, category, link_status


def _row_from_deal(deal, registry, acc):
    family, label, param_key, strategy_id, category, link_status = _link_fields(deal, registry)
    magic = int(getattr(deal, 'magic', 0) or 0)
    return (
        int(getattr(deal, 'ticket', 0) or 0),
        int(getattr(deal, 'order', 0) or 0),
        int(getattr(deal, 'position_id', 0) or 0),
        getattr(deal, 'symbol', None),
        magic,
        family, label, param_key, strategy_id, category,
        int(getattr(deal, 'entry', -1)),
        int(getattr(deal, 'type', -1)),
        float(getattr(deal, 'volume', 0.0) or 0.0),
        float(getattr(deal, 'price', 0.0) or 0.0),
        float(getattr(deal, 'profit', 0.0) or 0.0),
        float(getattr(deal, 'commission', 0.0) or 0.0),
        float(getattr(deal, 'swap', 0.0) or 0.0),
        float(getattr(deal, 'fee', 0.0) or 0.0),
        getattr(deal, 'comment', None),
        int(getattr(deal, 'time', 0) or 0),
        int(getattr(deal, 'time_msc', 0) or 0),
        acc.get('login'), acc.get('server'), acc.get('currency'),
        1 if MAGIC_POOL_LO <= magic <= MAGIC_POOL_HI else 0,
        link_status,
        datetime.datetime.now().isoformat(timespec='seconds'),
    )


_SQL_UPSERT = """
INSERT INTO deals (
    deal_ticket, order_ticket, position_id, symbol, magic,
    family, label, param_key, strategy_id, category,
    entry, deal_type, volume, price, profit, commission, swap, fee, comment,
    time, time_msc, account_login, account_server, account_currency,
    is_ours, link_status, ingested_at
) VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?,?,?,?,?, ?,?,?,?,?, ?,?,?)
ON CONFLICT(deal_ticket) DO UPDATE SET
    order_ticket=excluded.order_ticket, position_id=excluded.position_id,
    symbol=excluded.symbol, magic=excluded.magic,
    family=excluded.family, label=excluded.label, param_key=excluded.param_key,
    strategy_id=excluded.strategy_id, category=excluded.category,
    entry=excluded.entry, deal_type=excluded.deal_type, volume=excluded.volume,
    price=excluded.price, profit=excluded.profit, commission=excluded.commission,
    swap=excluded.swap, fee=excluded.fee, comment=excluded.comment,
    time=excluded.time, time_msc=excluded.time_msc,
    account_login=excluded.account_login, account_server=excluded.account_server,
    account_currency=excluded.account_currency,
    is_ours=excluded.is_ours, link_status=excluded.link_status,
    ingested_at=excluded.ingested_at
"""


def _account_dict():
    if mt5 is None:
        return {}
    try:
        acc = mt5.account_info()
        if acc is None:
            return {}
        return {'login': int(acc.login), 'server': acc.server, 'currency': acc.currency}
    except Exception:
        return {}


def _snapshot_registry(con, registry):
    """Сохранить снимок реестра (для аудита magic→стратегия во времени)."""
    if not registry:
        return
    now = datetime.datetime.now().isoformat(timespec='seconds')
    rows = [(m, r['symbol'], r['family'], r['param_key'], r['label'],
             r['activated_at'], r['deactivated_at'], r['conflict'], now)
            for m, r in registry.items()]
    con.executemany(
        "INSERT OR REPLACE INTO registry_snapshot "
        "(magic, symbol, type, param_key, label, activated_at, deactivated_at, conflict, snapshot_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()


def ingest(days=7, path=None, verbose=True):
    """Добрать сделки из MT5-истории в БД. Возвращает число обработанных deals (0 при сбое).

    Окно: от max(последний ingest, now-days) с суточным перехлёстом — ничего не теряем.
    """
    if mt5 is None:
        if verbose:
            print("  [trades_db] MetaTrader5 недоступен — ingest пропущен", flush=True)
        return 0
    try:
        con = connect(path)
        ensure_schema(con)
        registry = load_registry()

        from_dt = datetime.datetime.now() - datetime.timedelta(days=int(days))
        row = con.execute("SELECT last_time FROM ingest_log WHERE id=1").fetchone()
        if row and row['last_time']:
            resume = datetime.datetime.fromtimestamp(int(row['last_time'])) - datetime.timedelta(days=1)
            if resume > from_dt:
                from_dt = resume

        # +6ч к «сейчас», как в main.py — страховка от сдвига серверного времени
        to_dt = datetime.datetime.now() + datetime.timedelta(hours=6)
        deals = mt5.history_deals_get(from_dt, to_dt) or []
        acc = _account_dict()

        payload = []
        for d in deals:
            try:
                payload.append(_row_from_deal(d, registry, acc))
            except Exception:
                continue  # одна кривая сделка не должна ронять весь батч
        if payload:
            con.executemany(_SQL_UPSERT, payload)
        _snapshot_registry(con, registry)

        max_time = con.execute("SELECT MAX(time) AS t FROM deals").fetchone()['t'] or 0
        total = con.execute("SELECT COUNT(*) AS n FROM deals").fetchone()['n']
        con.execute(
            "INSERT INTO ingest_log (id, last_time, last_run, rows_total) VALUES (1, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET last_time=excluded.last_time, "
            "last_run=excluded.last_run, rows_total=excluded.rows_total",
            (int(max_time), datetime.datetime.now().isoformat(timespec='seconds'), int(total)))
        con.commit()
        con.close()

        if verbose:
            print(f"  [trades_db] ingest: получено {len(payload)} сдел(ок) из MT5, "
                  f"в БД всего {total} (окно от {from_dt:%Y-%m-%d %H:%M})", flush=True)
        return len(payload)
    except Exception as exc:
        if verbose:
            print(f"  [trades_db] ingest не выполнен: {exc!r}", flush=True)
        return 0


def stats(path=None, verbose=True):
    """Краткая сводка по БД. Возвращает dict."""
    out = {}
    try:
        if not os.path.exists(db_path(path)):
            if verbose:
                print(f"  [trades_db] нет файла БД: {db_path(path)}", flush=True)
            return out
        con = connect(path, readonly=True)
        if not _table_exists(con, 'deals'):
            con.close()
            if verbose:
                print("  [trades_db] таблицы deals ещё нет — БД пустая/не создана", flush=True)
            return out
        q = con.execute("""
            SELECT COUNT(*) AS deals,
                   COUNT(DISTINCT position_id) AS positions,
                   COUNT(DISTINCT magic) AS magics,
                   MIN(time) AS t_min, MAX(time) AS t_max,
                   SUM(CASE WHEN link_status='unlinked' THEN 1 ELSE 0 END) AS unlinked,
                   SUM(CASE WHEN is_ours=1 THEN 1 ELSE 0 END) AS ours,
                   ROUND(SUM(profit+commission+swap+fee), 2) AS pnl_net
            FROM deals
        """).fetchone()
        out = {k: q[k] for k in q.keys()}
        acc = con.execute(
            "SELECT DISTINCT account_login, account_server, account_currency FROM deals").fetchall()
        out['accounts'] = [dict(a) for a in acc]
        con.close()
        if verbose:
            def _ts(v):
                return datetime.datetime.fromtimestamp(v).strftime('%Y-%m-%d %H:%M') if v else '-'
            print(f"  [trades_db] {db_path(path)}", flush=True)
            print(f"    deals={out['deals']} positions={out['positions']} magics={out['magics']} "
                  f"unlinked={out['unlinked']} ours={out['ours']} PnL_net={out['pnl_net']}", flush=True)
            print(f"    период: {_ts(out['t_min'])} … {_ts(out['t_max'])}", flush=True)
            for a in out['accounts']:
                print(f"    аккаунт: {a['account_login']} @ {a['account_server']} "
                      f"({a['account_currency']})", flush=True)
    except Exception as exc:
        if verbose:
            print(f"  [trades_db] stats не выполнен: {exc!r}", flush=True)
    return out


def _category_of(symbol, magic, registry):
    """sid категории штурвала (symbol_family). Непривязанный magic → symbol_?."""
    rec = registry.get(_safe_int(magic, -1))
    family = rec['family'] if rec else None
    return f"{symbol}_{family}" if family else f"{symbol}_?"


def _day_bounds(day_str):
    """[start, end) unix-границы локального дня 'YYYY-MM-DD'."""
    d = datetime.datetime.strptime(day_str, '%Y-%m-%d')
    start = int(d.timestamp())
    return start, start + 86400


# UPSERT пиков через MAX(peak_*)/MIN(min_*): храним ЛУЧШУЮ и ХУДШУЮ точку дня.
_SQL_PEAK_UPSERT = """
INSERT INTO daily_peak (
    day, account_login, category,
    peak_float, peak_ts, peak_volume, peak_per_lot,
    min_float, min_ts, realized_net, samples
) VALUES (?,?,?, ?,?,?,?, ?,?,?,?)
ON CONFLICT(day, account_login, category) DO UPDATE SET
    peak_float   = CASE WHEN excluded.peak_float > daily_peak.peak_float
                        THEN excluded.peak_float ELSE daily_peak.peak_float END,
    peak_ts      = CASE WHEN excluded.peak_float > daily_peak.peak_float
                        THEN excluded.peak_ts ELSE daily_peak.peak_ts END,
    peak_volume  = CASE WHEN excluded.peak_float > daily_peak.peak_float
                        THEN excluded.peak_volume ELSE daily_peak.peak_volume END,
    peak_per_lot = CASE WHEN excluded.peak_float > daily_peak.peak_float
                        THEN excluded.peak_per_lot ELSE daily_peak.peak_per_lot END,
    min_float    = CASE WHEN excluded.min_float < daily_peak.min_float
                        THEN excluded.min_float ELSE daily_peak.min_float END,
    min_ts       = CASE WHEN excluded.min_float < daily_peak.min_float
                        THEN excluded.min_ts ELSE daily_peak.min_ts END,
    realized_net = excluded.realized_net,
    samples      = daily_peak.samples + 1
"""


def sample_positions(interval=None, path=None, verbose=True):
    """Сэмплер открытых позиций: обновляет daily_peak и equity_samples.

    Разрезы:
      equity_samples — 1 строка на вызов: общий floating счёта во времени;
      daily_peak     — 1 строка на (день, аккаунт, категория): экстремумы MAX/MIN.

    interval — интервал планирования (его соблюдает вызывающая сторона, напр. main);
    сама функция только делает один сэмпл. Fail-safe: ошибка → 0, пайплайн не падает.
    """
    if mt5 is None:
        if verbose:
            print("  [trades_db] MetaTrader5 недоступен — sample пропущен", flush=True)
        return 0
    try:
        acc = mt5.account_info()
        if acc is None:
            return 0
        positions = mt5.positions_get() or []
        login = int(acc.login)
        now_ts = int(datetime.datetime.now().timestamp())
        day = datetime.datetime.now().strftime('%Y-%m-%d')
        registry = load_registry()

        # floating (profit+swap) по категориям + суммарный объём
        per_cat = {}
        floating_total = 0.0
        for p in positions:
            try:
                pl = float(getattr(p, 'profit', 0.0) or 0.0) + float(getattr(p, 'swap', 0.0) or 0.0)
                vol = float(getattr(p, 'volume', 0.0) or 0.0)
            except Exception:
                continue  # одна кривая позиция — не роняем весь сэмпл
            floating_total += pl
            cat = _category_of(getattr(p, 'symbol', '') or '', getattr(p, 'magic', 0), registry)
            slot = per_cat.setdefault(cat, {'float': 0.0, 'vol': 0.0})
            slot['float'] += pl
            slot['vol'] += vol

        con = connect(path)
        ensure_schema(con)

        # 1) снимок счёта (разрез «1 строка на тик семплера»)
        con.execute(
            "INSERT INTO equity_samples "
            "(ts, account_login, balance, equity, floating_total, n_positions) "
            "VALUES (?,?,?,?,?,?)",
            (now_ts, login,
             float(getattr(acc, 'balance', 0.0) or 0.0),
             float(getattr(acc, 'equity', 0.0) or 0.0),
             floating_total, len(positions)))

        # 2) реализованное за день по категориям (для give-back: peak vs realized)
        realized = {}
        try:
            start, end = _day_bounds(day)
            for r in con.execute(
                    "SELECT category, SUM(profit+commission+swap+fee) AS net FROM deals "
                    "WHERE time >= ? AND time < ? AND category IS NOT NULL GROUP BY category",
                    (start, end)):
                realized[r['category']] = float(r['net'] or 0.0)
        except Exception:
            realized = {}

        # 3) экстремумы floating по категориям (разрез «1 строка на день/аккаунт/категорию»)
        rows = []
        for cat, slot in per_cat.items():
            vol = slot['vol']
            per_lot = (slot['float'] / vol) if vol > 0 else None
            rows.append((day, login, cat,
                         slot['float'], now_ts, vol, per_lot,
                         slot['float'], now_ts, realized.get(cat, 0.0), 1))
        if rows:
            con.executemany(_SQL_PEAK_UPSERT, rows)

        con.commit()
        con.close()
        if verbose:
            print(f"  [trades_db] sample: позиций {len(positions)}, "
                  f"floating {floating_total:+,.0f}, категорий {len(per_cat)}", flush=True)
        return len(positions)
    except Exception as exc:
        if verbose:
            print(f"  [trades_db] sample не выполнен: {exc!r}", flush=True)
        return 0


def vacuum_into(out_path=None, path=None, verbose=True):
    """Консистентный снапшот БД одним файлом (VACUUM INTO) — безопасно копировать даже при открытой БД."""
    try:
        src = db_path(path)
        dst = out_path or os.path.join(os.path.dirname(src), 'trades_snapshot.db')
        if not os.path.exists(src):
            if verbose:
                print(f"  [trades_db] нет файла БД: {src}", flush=True)
            return None
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        con = connect(src)
        _safe = dst.replace("'", "''")
        con.execute(f"VACUUM INTO '{_safe}'")
        con.close()
        if verbose:
            print(f"  [trades_db] снапшот: {dst}", flush=True)
        return dst
    except Exception as exc:
        if verbose:
            print(f"  [trades_db] vacuum не выполнен: {exc!r}", flush=True)
        return None


def record_position(position_ticket, path=None, verbose=False):
    """Записать сделки ОДНОЙ закрытой позиции сразу после закрытия.

    Точечный pull: mt5.history_deals_get(position=ticket) → upsert (идемпотентно).
    Ночной ingest остаётся страховкой: если на момент закрытия выход-сделка ещё
    не видна в истории, её доберёт ближайший ingest (UPSERT, дублей не будет).
    Fail-safe: любая ошибка → 0, торговлю не трогает.
    """
    if mt5 is None or not position_ticket:
        return 0
    try:
        deals = mt5.history_deals_get(position=int(position_ticket)) or []
        if not deals:
            return 0
        con = connect(path)
        ensure_schema(con)
        registry = load_registry()
        acc = _account_dict()
        payload = []
        for d in deals:
            try:
                payload.append(_row_from_deal(d, registry, acc))
            except Exception:
                continue  # одна кривая сделка не роняет запись
        if payload:
            con.executemany(_SQL_UPSERT, payload)
            con.commit()
        con.close()
        if verbose:
            print(f"  [trades_db] record_position {int(position_ticket)}: {len(payload)} deal(ок)", flush=True)
        return len(payload)
    except Exception as exc:
        if verbose:
            print(f"  [trades_db] record_position не выполнен: {exc!r}", flush=True)
        return 0


def main():
    ap = argparse.ArgumentParser(description='История сделок StrategyCloud в SQLite')
    sub = ap.add_subparsers(dest='cmd')
    p_i = sub.add_parser('ingest', help='добрать сделки из MT5-истории')
    p_i.add_argument('--days', type=int, default=7)
    p_s = sub.add_parser('stats', help='сводка по БД')
    p_sm = sub.add_parser('sample', help='сэмпл открытых позиций: daily_peak + equity_samples')
    p_v = sub.add_parser('vacuum', help='консистентный снапшот файла БД')
    p_v.add_argument('--out', default=None)
    for p in (p_i, p_s, p_sm, p_v):
        p.add_argument('--db', default=None)
    args = ap.parse_args()

    if args.cmd == 'ingest':
        ingest(days=args.days, path=args.db)
    elif args.cmd == 'stats':
        stats(path=args.db)
    elif args.cmd == 'sample':
        sample_positions(path=args.db)
    elif args.cmd == 'vacuum':
        vacuum_into(out_path=args.out, path=args.db)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
