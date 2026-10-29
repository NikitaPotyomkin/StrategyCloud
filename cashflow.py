"""Движения средств по счёту (пополнения / выводы / корректировки).

Задача: отделить ВНЕШНИЕ деньги от торгового результата, чтобы метрики
(доходность, equity, дневной стоп) не «взрывались» после пополнения.

Правило: движением средств считается всё, что меняет баланс, но НЕ является
торговой сделкой: DEAL_TYPE_BALANCE (депо/вывод), CREDIT (кредит/бонус),
CHARGE (плата брокера), CORRECTION (правка баланса), BONUS.
Комиссии и свопы ТОРГОВЫХ сделок сюда не попадают — они уже внутри profit_net.

Демо-ловушка: перезапись баланса в кабинете может НЕ попасть в историю сделок.
Поэтому есть второй механизм — reconcile(): сравнивает фактический баланс с
ожидаемым (прошлый баланс + Σ торговых сделок) и фиксирует расхождение как
операцию с source='reconcile'.

Третий механизм — bootstrap(): точка отсчёта внешних денег при первом запуске.

Период учёта (CUTOFF_BY_LOGIN): на счёте могут остаться «исторические» события
(демо-пересоздания, сбросы) — они не имеют отношения к текущей торговле.
Для таких счетов задаётся дата начала учёта: всё, что раньше, сворачивается в
одну операцию «входящий остаток» (kind='opening', source='cutoff'), а сами
старые события удаляются из balance_ops. Баланс на момент отсечки считается
как сумма ВСЕХ сделок до этой даты.

Таблица balance_ops живёт в той же SQLite (journals/trades.db), идемпотентна
по op_key. Модуль ничего не импортирует из проекта, кроме trades_db.connect,
поэтому его можно безопасно подключать постепенно.
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, 'journals', 'cashflow_state.json')

# С какого момента считать внешние деньги: логин → 'YYYY-MM-DD' (серверная дата).
# Всё, что раньше, сворачивается в «входящий остаток» и не попадает в пополнения.
CUTOFF_BY_LOGIN = {
    2000066590: '2026-09-29',   # AlfaForexRU: период учёта (раньше — демо-сбросы/пересоздание)   # AlfaForexRU: до этого были демо-сбросы и пересоздание
}

# Типы сделок MT5, которые считаются движением средств (не торговлей).
OP_TYPES = {}
try:                                   # константы берём из API, если он есть
    import MetaTrader5 as mt5
    for _name in ('DEAL_TYPE_BALANCE', 'DEAL_TYPE_CREDIT', 'DEAL_TYPE_CHARGE',
                  'DEAL_TYPE_CORRECTION', 'DEAL_TYPE_BONUS'):
        _v = getattr(mt5, _name, None)
        if _v is not None:
            OP_TYPES[int(_v)] = _name.replace('DEAL_TYPE_', '').lower()
except Exception:                      # офлайн-режим: работаем по известным кодам
    OP_TYPES = {2: 'balance', 3: 'credit', 4: 'charge', 5: 'correction', 6: 'bonus'}

TRADE_TYPES = {0: 'buy', 1: 'sell'}    # DEAL_TYPE_BUY / DEAL_TYPE_SELL
TOLERANCE_RUB = 1.0                    # расхождение меньше — шум округления
RECONCILE_LOOKBACK = 12 * 3600          # окно перекрытия для поиска сделок, сек

DDL = """
CREATE TABLE IF NOT EXISTS balance_ops (
    op_key      TEXT PRIMARY KEY,   -- ticket сделки либо synthetic:<ts>/bootstrap:<login>
    account_login INTEGER,
    ts          INTEGER,            -- серверное время, unix
    amount      REAL,               -- + пополнение, − вывод
    kind        TEXT,               -- balance|credit|charge|correction|bonus|opening|reconcile
    source      TEXT,               -- 'deals' | 'reconcile' | 'bootstrap' | 'cutoff'
    ticket      INTEGER,
    comment     TEXT,
    recorded_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_balance_ops_ts ON balance_ops(ts);
"""

_MT5_READY = None                      # кэш подключения к терминалу (на процесс)


def _ensure_mt5():
    """Один раз за процесс проверяет/поднимает подключение к терминалу MT5.

    Без initialize() функции MetaTrader5 возвращают None, а не бросают
    исключение — поэтому без этой проверки модуль молча видел «пустую историю».
    """
    global _MT5_READY
    if _MT5_READY is not None:
        return _MT5_READY
    try:
        import MetaTrader5 as _mt5
        if _mt5.terminal_info() is not None:
            _MT5_READY = True
        elif _mt5.initialize():
            _MT5_READY = True
        else:
            print(f"  [cashflow] MT5 не инициализирован: {_mt5.last_error()} "
                  "(терминал запущен?)", flush=True)
            _MT5_READY = False
    except Exception as exc:
        print(f"  [cashflow] MT5 недоступен: {exc!r}", flush=True)
        _MT5_READY = False
    return _MT5_READY


def _connect():
    """Соединение с журнальной БД (создаёт таблицу при первом обращении)."""
    import trades_db
    con = trades_db.connect()
    con.executescript(DDL)
    return con


def _account_login():
    try:
        import MetaTrader5 as _mt5
        acc = _mt5.account_info()
        return int(getattr(acc, 'login', 0) or 0) if acc else 0
    except Exception:
        return 0


def _cutoff_ts(login):
    """Начало периода учёта в «серверных» секундах (0 — учёт с самого начала)."""
    period = CUTOFF_BY_LOGIN.get(int(login or 0))
    if not period:
        return 0
    try:
        return int(datetime.strptime(str(period), '%Y-%m-%d')
                   .replace(tzinfo=timezone.utc).timestamp())
    except Exception:
        return 0


def _deal_net(d):
    """Вклад сделки в баланс: профит + своп + комиссия + сбор."""
    return (float(getattr(d, 'profit', 0.0) or 0.0)
            + float(getattr(d, 'swap', 0.0) or 0.0)
            + float(getattr(d, 'commission', 0.0) or 0.0)
            + float(getattr(d, 'fee', 0.0) or 0.0))


def record(ops, verbose=True):
    """Пишет операции в balance_ops. Идемпотентно: повтор не создаёт дублей."""
    if not ops:
        return 0
    written = 0
    con = _connect()
    try:
        for o in ops:
            try:
                amount = float(o.get('amount') or 0.0)
            except (TypeError, ValueError):
                continue
            if amount == 0:
                continue
            cur = con.execute(
                "INSERT OR IGNORE INTO balance_ops "
                "(op_key, account_login, ts, amount, kind, source, ticket, comment, recorded_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (str(o.get('op_key')), int(o.get('account_login') or 0),
                 int(o.get('ts') or 0), amount, str(o.get('kind') or 'balance'),
                 str(o.get('source') or 'deals'), int(o.get('ticket') or 0),
                 str(o.get('comment') or '')[:120],
                 datetime.now().strftime('%Y-%m-%dT%H:%M:%S')))
            if getattr(cur, 'rowcount', 0) > 0:
                written += 1
        con.commit()
    finally:
        con.close()
    if written and verbose:
        print(f"  [cashflow] записано операций: {written}", flush=True)
    return written


def fetch_deals(since_dt=None, until_dt=None):
    """Операции из истории сделок MT5 (всё, что не торговля).

    События раньше начала периода учёта отбрасываются — они свёрнуты в
    «входящий остаток».
    """
    out = []
    if not _ensure_mt5():
        return out
    import MetaTrader5 as _mt5
    if since_dt is None:
        since_dt = datetime.now() - timedelta(days=30)
    if until_dt is None:
        until_dt = datetime.now() + timedelta(hours=6)
    deals = _mt5.history_deals_get(since_dt, until_dt)
    if deals is None:
        print(f"  [cashflow] история сделок недоступна: {_mt5.last_error()}", flush=True)
        return out
    login = _account_login()
    cut = _cutoff_ts(login)
    for d in deals:
        _type = int(getattr(d, 'type', -1))
        if _type not in OP_TYPES:           # торговые сделки (buy/sell) сюда не идут
            continue
        ts = int(getattr(d, 'time', 0) or 0)
        if cut and ts < cut:
            continue                        # до начала периода учёта
        amount = float(getattr(d, 'profit', 0.0) or 0.0)
        if amount == 0:
            continue
        out.append({
            'op_key': f"deal:{int(getattr(d, 'ticket', 0))}",
            'account_login': login,
            'ts': ts,
            'amount': amount,
            'kind': OP_TYPES[_type],
            'source': 'deals',
            'ticket': int(getattr(d, 'ticket', 0)),
            'comment': str(getattr(d, 'comment', '') or ''),
        })
    return out


def _load_state():
    try:
        with open(STATE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def purge_before_cutoff(verbose=True):
    """Убирает из balance_ops операции, попавшие туда до начала периода учёта."""
    if not _ensure_mt5():
        return 0
    login = _account_login()
    cut = _cutoff_ts(login)
    if not cut:
        return 0
    con = _connect()
    try:
        cur = con.execute("DELETE FROM balance_ops WHERE account_login = ? AND ts < ?",
                          (login, cut))
        n = int(getattr(cur, 'rowcount', 0) or 0)
        con.commit()
    finally:
        con.close()
    if n and verbose:
        print(f"  [cashflow] период учёта с {CUTOFF_BY_LOGIN.get(login)}: "
              f"старых операций убрано {n}", flush=True)
    return n


def bootstrap(verbose=True):
    """Точка отсчёта внешних денег.

    Если для счёта задан период учёта (CUTOFF_BY_LOGIN): входящий остаток =
    баланс на момент отсечки, то есть сумма ВСЕХ сделок до этой даты. Пишется
    одной операцией kind='opening', source='cutoff'.

    Если периода нет: входящий остаток = баланс сейчас − Σ всей истории сделок,
    то есть деньги, которые брокер не отразил как операцию.
    Возвращает число записанных строк (0 или 1).
    """
    if not _ensure_mt5():
        return 0
    import MetaTrader5 as _mt5
    acc = _mt5.account_info()
    if acc is None:
        print("  [cashflow] нет данных счёта", flush=True)
        return 0
    deals = _mt5.history_deals_get(datetime(2000, 1, 1),
                                   datetime.now() + timedelta(hours=6)) or ()
    login = int(getattr(acc, 'login', 0) or 0)
    balance = float(acc.balance)
    cut = _cutoff_ts(login)
    state = _load_state()

    if cut:
        opening = 0.0
        for d in deals:
            if int(getattr(d, 'time', 0) or 0) < cut:
                opening += _deal_net(d)
        period = CUTOFF_BY_LOGIN.get(login)
        state['period_start'] = period
        state['opening_balance'] = round(opening, 2)
        state['initial_capital'] = round(opening, 2)
        state['bootstrap_deals'] = len(deals)
        _save_state(state)
        if verbose:
            print(f"  [cashflow] период учёта с {period}: входящий остаток "
                  f"{opening:+,.2f} RUB (баланс сейчас {balance:,.2f}; "
                  f"сделок в истории {len(deals)})", flush=True)
        if abs(opening) < TOLERANCE_RUB:
            return 0
        return record([{
            'op_key': f"opening:{login}:{period}",
            'account_login': login,
            'ts': cut,
            'amount': round(opening, 2),
            'kind': 'opening',
            'source': 'cutoff',
            'ticket': 0,
            'comment': f"входящий остаток на {period} (события до отсечки свёрнуты)",
        }], verbose=verbose)

    net = 0.0
    first_ts = 0
    for d in deals:
        d_ts = int(getattr(d, 'time', 0) or 0)
        if d_ts and (first_ts == 0 or d_ts < first_ts):
            first_ts = d_ts
        net += _deal_net(d)
    residual = balance - net
    state['initial_capital'] = round(residual, 2)
    state['bootstrap_deals'] = len(deals)
    _save_state(state)
    if verbose:
        print(f"  [cashflow] база: капитал вне истории {residual:+,.2f} RUB "
              f"(баланс {balance:,.2f}; сделок в истории {len(deals)}, "
              f"их итог {net:+,.2f})", flush=True)
    if abs(residual) < TOLERANCE_RUB:
        return 0
    return record([{
        'op_key': f"bootstrap:{login}",
        'account_login': login,
        'ts': first_ts or (int(time.time()) - 86400),
        'amount': round(residual, 2),
        'kind': 'balance',
        'source': 'bootstrap',
        'ticket': 0,
        'comment': 'капитал на старте учёта (баланс минус итог истории сделок)',
    }], verbose=verbose)


def reconcile(balance_now, verbose=True):
    """Ловит движения средств, которых нет в истории сделок (демо-перезапись).

    expected = last_balance + Σ торговых сделок, появившихся после прошлой сверки.
    Расхождение больше допуска → синтетическая операция source='reconcile'.

    last_check_ts хранится в СЕРВЕРНОМ времени (как время сделок), поэтому
    окно не съезжает на разницу UTC/сервер, а сделки, уже учтённые в прошлой
    сверке, повторно не суммируются.
    """
    if not _ensure_mt5():
        return 0
    import MetaTrader5 as _mt5
    state = _load_state()
    last_ts = int(state.get('last_check_ts') or 0)
    last_balance = state.get('last_balance')
    since = (datetime.fromtimestamp(max(0, last_ts - RECONCILE_LOOKBACK))
             if last_ts else datetime.now() - timedelta(days=1))
    deals = _mt5.history_deals_get(since, datetime.now() + timedelta(hours=6)) or ()
    trade_pnl = 0.0
    fresh_ts = last_ts
    for d in deals:
        d_ts = int(getattr(d, 'time', 0) or 0)
        if d_ts > fresh_ts:
            fresh_ts = d_ts
        if d_ts and last_ts and d_ts < last_ts:
            continue                       # уже учтено в прошлой сверке
        if int(getattr(d, 'type', -1)) in TRADE_TYPES:
            trade_pnl += _deal_net(d)
    ops = []
    if last_balance is not None and balance_now is not None:
        unexplained = float(balance_now) - float(last_balance) - trade_pnl
        if abs(unexplained) >= TOLERANCE_RUB:
            ts = int(time.time())
            ops.append({
                'op_key': f"synthetic:{ts}",
                'account_login': _account_login(),
                'ts': ts,
                'amount': round(unexplained, 2),
                'kind': 'reconcile',
                'source': 'reconcile',
                'ticket': 0,
                'comment': f"unexplained balance delta (trades {trade_pnl:+.2f})",
            })
            if verbose:
                print(f"  [cashflow] сверка: необъяснимое движение {unexplained:+,.2f} RUB "
                      f"(баланс {float(balance_now):,.2f}, было {float(last_balance):,.2f}, "
                      f"торговля {trade_pnl:+,.2f})", flush=True)
    elif verbose:
        print("  [cashflow] сверка: точка отсчёта ещё не задана — фиксирую баланс", flush=True)
    state['last_balance'] = float(balance_now) if balance_now is not None else last_balance
    state['last_check_ts'] = int(fresh_ts or time.time())
    _save_state(state)
    return record(ops, verbose=verbose)


def sync(balance_now=None, days=30, verbose=True):
    """Полный проход: точка отсчёта + история сделок + сверка баланса.

    Первый проход читает историю ЦЕЛИКОМ (с 2000-01-01): иначе стартовое
    пополнение счёта, сделанное когда-то давно, в базу не попадает и «за всё
    время» превращается в «за 30 дней». Дальше окно короткое — по days.
    """
    if not _ensure_mt5():
        return 0
    if balance_now is None:
        try:
            import MetaTrader5 as _mt5
            acc = _mt5.account_info()
            balance_now = float(acc.balance) if acc else None
        except Exception:
            balance_now = None
    state = _load_state()
    login = _account_login()
    cut = _cutoff_ts(login)
    if cut:
        purge_before_cutoff(verbose=verbose)
        if state.get('opening_period') != CUTOFF_BY_LOGIN.get(login):
            bootstrap(verbose=verbose)
            state = _load_state()
            state['opening_period'] = CUTOFF_BY_LOGIN.get(login)
            _save_state(state)
    elif state.get('last_balance') is None:
        bootstrap(verbose=verbose)
    n = 0
    if not state.get('history_loaded'):
        ops = fetch_deals(since_dt=datetime(2000, 1, 1))   # вся история, один раз
        n += record(ops, verbose=verbose)
        state = _load_state()
        state['history_loaded'] = int(time.time())
        _save_state(state)
        if verbose:
            print(f"  [cashflow] история загружена целиком: операций {len(ops)}", flush=True)
    else:
        ops = fetch_deals(since_dt=datetime.now() - timedelta(days=days))
        n += record(ops, verbose=verbose)
    n += reconcile(balance_now, verbose=verbose)
    return n


def maybe_sync(min_gap=300, balance_now=None, verbose=False):
    """Синк не чаще одного раза в min_gap секунд.

    Нужен для минутных циклов бота и для дэшборда: вызывать можно сколько
    угодно часто, реальная работа (история сделок + сверка) выполнится только
    если с прошлого прохода прошло min_gap секунд. Возвращает число записанных
    операций (0 — если ещё рано или ничего нового).
    """
    state = _load_state()
    last = int(state.get('last_sync_ts') or 0)
    if last and (int(time.time()) - last) < int(min_gap):
        return 0
    n = sync(balance_now=balance_now, days=30, verbose=verbose)
    state = _load_state()
    state['last_sync_ts'] = int(time.time())
    _save_state(state)
    return n


def ops_list(from_ts=None, to_ts=None, limit=200):
    """Список операций (для дэшборда): [(ts, amount, kind, source, comment)]."""
    where, args = [], []
    if from_ts:
        where.append('ts >= ?'); args.append(int(from_ts))
    if to_ts:
        where.append('ts < ?'); args.append(int(to_ts))
    q = ("SELECT ts, amount, kind, source, comment FROM balance_ops"
         + (" WHERE " + " AND ".join(where) if where else "")
         + f" ORDER BY ts DESC LIMIT {int(limit)}")
    con = _connect()
    try:
        return list(con.execute(q, args))
    finally:
        con.close()


def summary(from_ts=None, to_ts=None, account_login=None):
    """(пополнения, выводы, нетто, число операций) за окно.

    «Пополнения» включают входящий остаток на начало периода учёта — это тоже
    внешние деньги, просто внесённые до отсечки.
    """
    where, args = [], []
    if from_ts:
        where.append('ts >= ?'); args.append(int(from_ts))
    if to_ts:
        where.append('ts < ?'); args.append(int(to_ts))
    if account_login:
        where.append('account_login = ?'); args.append(int(account_login))
    q = ("SELECT amount FROM balance_ops"
         + (" WHERE " + " AND ".join(where) if where else ""))
    deposit = withdraw = 0.0
    n = 0
    con = _connect()
    try:
        for (amount,) in con.execute(q, args):
            v = float(amount or 0.0)
            n += 1
            if v > 0:
                deposit += v
            else:
                withdraw += v
    finally:
        con.close()
    return deposit, withdraw, deposit + withdraw, n


if __name__ == '__main__':
    import sys
    _cmd = sys.argv[1] if len(sys.argv) > 1 else 'sync'
    if not _ensure_mt5():
        print("нет подключения к терминалу MT5 — нечего синхронизировать")
        sys.exit(2)
    import MetaTrader5 as _mt5
    _acc = _mt5.account_info()
    if _acc is not None:
        print(f"счёт {_acc.login} ({_acc.server}), баланс {_acc.balance:,.2f} {_acc.currency}")
    if _cmd == 'sync':
        print(f"операций записано: {sync()}")
    elif _cmd == 'ops':
        for _ts, _amt, _kind, _src, _cmt in ops_list(limit=20):
            _when = datetime.fromtimestamp(_ts).strftime('%Y-%m-%d %H:%M')
            print(f"  {_when}  {_amt:+12,.2f}  {_kind:<10} [{_src}]  {_cmt}")
    dep, wd, net, cnt = summary()
    _period = CUTOFF_BY_LOGIN.get(int(getattr(_acc, 'login', 0) or 0)) if _acc else None
    _tail = f" (период учёта с {_period})" if _period else ""
    print(f"за всё время{_tail}: пополнения {dep:+,.0f} ₽, выводы {wd:+,.0f} ₽, "
          f"нетто {net:+,.0f} ₽, операций {cnt}")
    if _acc is not None:
        _res = float(_acc.balance) - net
        print(f"торговый результат за период: {_res:+,.0f} ₽ "
              f"(баланс {float(_acc.balance):,.2f} − внешние деньги {net:,.2f})")
