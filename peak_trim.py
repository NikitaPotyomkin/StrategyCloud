"""Пик-трим: ОЦЕНКА правила «фиксируем по историческому пику удельной прибыли».

Замысел (согласован 26.10):
  сделка идёт внутри дня и по удельной прибыли (₽ на лот) проходит 55к → 75к →
  90к ₽/лот. По истории ДНЕЙ есть эталон — МАКСИМУМ удельной прибыли дня за всё
  время (сейчас ≈ 12 409 ₽/лот), а не прибыль одной сделки. Как только удельная
  прибыль СЧЁТА (потенциал дня / плановый объём дня) доходит до pct (100%) эталона —
  режем ВСЕ позиции до 0.01 лот, остаток доживает до TP/SL, чтобы видеть, докуда
  дошла бы история. Эталон со временем поднимается сам.






  ВКЛЮЧЕНО с 30.10: реальные закрытия до keep_volume (PeakTrimParams.enabled=True).
  Модуль считает решения, пишет их в таблицу peak_trim (mode='shadow') и умеет
  показать, как часто правило сработало бы на уже накопленной истории.

Откуда данные:
  trades_db.sample_positions() каждые ~300 с пишет в position_peak 1 строку на
  (день, аккаунт, position_id) с peak_float / peak_per_lot. Именно peak_per_lot
  (₽ на лот) — объёмно-инвариантная величина, поэтому 0.01 и 1.0 лот сравнимы.

Что делает scan_and_trim() (на каждом тике сэмплера):
  1) эталон = ref_quantile(удельная прибыль ДНЯ из equity_samples) за lookback_days
     (lookback_days = 0 → вся история с начала работы робота, since 29.09.2026);
  2) считает удельную прибыль ДНЯ сейчас: (реализованные сделки дня + плавающая
     открытых позиций) / ПЛАНОВЫЙ объём дня — как на графике Risk;
  3) ratio = удельная_дня / эталон; если ratio >= pct — в лог идёт
     `[TRIM] REAL/would …` (и событие в peak_trim) → РЕЖЕМ ВСЕ позиции своих
     magic до keep_volume; остаток доживает до своего TP/SL;
  4) повторно позицию в тот же день не считает (single_shot).

Что делает evaluate() (CLI --eval):
  проходит по истории день за днём, для каждого дня берёт эталон по ПРЕДЫДУЩИМ
  дням и считает, у скольких сделок их ЗАСЕЧЁННЫЙ пик превысил 70/75/80/85/90%
  эталона. Это ответ на «как часто правило вообще срабатывает» — до того, как
  включать его в торги.

Безопасность:
  • enabled=False — закрытий нет, только лог и запись решения (сейчас True);
  • трогаем только позиции со «стратегическим» magic (770000..869999);
  • не трогаем объём <= keep_volume; при хите прибыль позиции уже не важна;
  • эталон считается БЕЗ сегодняшнего дня — нет подглядывания в будущее;
  • ошибка по одной позиции не роняет ни сэмплер, ни торговый цикл.

ВНИМАНИЕ: фиксация по пику не гарантирует лучший выход — цена после закрытия
может уйти и дальше (именно это и измеряет остаток 0.01 лот), а сам пик
засекается с шагом сэмплера (5 мин), поэтому фактический экстремум мог быть выше.
"""

import datetime
import json
import math
import os

from config import PeakTrimParams

# «Стратегические» magic: чужие/ручные сделки не трогаем
_MIN_MAGIC = 770000
_MAX_MAGIC = 869999

# Серверное время = UTC+3 (та же граница суток, что в equity_samples/риск-блоке)
SRV_OFFSET_H = 3

# План на день — journals/active_state.json (собирает ночной реранк), а НЕ
# фактическая книга за сутки: порог трима в рублях должен быть один на день.
PLAN_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'journals', 'active_state.json')
PLAN_CACHE_SEC = 300      # как часто перечитывать файл плана (с)
PLAN_MAX_AGE_H = 26.0     # план старше — недостоверен (ночной реранк не прошёл)
_PLAN_CACHE = {'ts': 0.0, 'vol': 0.0, 'updated': ''}

# Порог, начиная с которого shadow-решение попадает в лог (доля эталона)
_EVAL_THRESHOLDS = (0.70, 0.75, 0.80, 0.85, 0.90)

_SQL_TRIM_TABLE = """
CREATE TABLE IF NOT EXISTS peak_trim (
    ts             INTEGER,
    day            TEXT,
    account_login  INTEGER,
    position_id    INTEGER,
    symbol         TEXT,
    family         TEXT,
    category       TEXT,
    magic          INTEGER,
    volume_before  REAL,
    volume_closed  REAL,
    volume_left    REAL,
    price          REAL,
    float_money    REAL,
    float_per_lot  REAL,
    ref_per_lot    REAL,
    ref_pct        REAL,
    ref_scope      TEXT,      -- 'account_day' (удельная прибыль ДНЯ по счёту)
    ref_last_day   TEXT,
    mode           TEXT,      -- 'shadow' (только лог) | 'real' | 'failed'
    retcode        INTEGER,
    result_comment TEXT
);
CREATE INDEX IF NOT EXISTS ix_trim_day ON peak_trim(day);
CREATE INDEX IF NOT EXISTS ix_trim_pos ON peak_trim(position_id);
"""


def _ensure_table(con):
    """Таблица событий пик-трима (создаётся лениво, схему trades_db не трогаем)."""
    con.executescript(_SQL_TRIM_TABLE)


def _space(value, nd=0):
    """Число с пробелами между разрядами — как в остальных логах проекта."""
    try:
        return f"{float(value):,.{nd}f}".replace(',', ' ')
    except (TypeError, ValueError):
        return '—'


def _pct(values, q):
    """Квантиль (линейная интерполяция) — без numpy, чтобы не тянуть зависимость."""
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    q = min(max(float(q), 0.0), 1.0)
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(xs[lo])
    return float(xs[lo] + (xs[hi] - xs[lo]) * (pos - lo))


def _window_start(day_str, days):
    """Дата начала окна истории (день_str минус days дней).

    days <= 0 — окно НЕ ограничено: берём всю историю с начала работы робота
    (реально 29.09.2026), то есть без скользящего окна и без отсечки по дате.
    """
    if int(days or 0) <= 0:
        return '2020-01-01'  # безопасная минимальная дата
    try:
        return (datetime.date.fromisoformat(day_str)
                - datetime.timedelta(days=int(days))).isoformat()
    except ValueError:
        return '2020-01-01'


def _win_label(cfg):
    """Текст окна эталона для логов: «30 дн.» либо «вся история» (lookback_days <= 0)."""
    d = int(getattr(cfg, 'lookback_days', 0) or 0)
    return f"{d} дн." if d > 0 else "вся история"


def _ref_label(cfg):
    """Эталон словами: «медиана дневных пиков» (0.50) / «максимум дневного пика»."""
    q = float(getattr(cfg, 'ref_quantile', 0.5) or 0.5)
    if abs(q - 0.5) < 1e-9:
        return "медиана дневных пиков"
    if abs(q - 1.0) < 1e-9:
        return "максимум дневного пика"
    return f"p{q * 100:.0f} дневных пиков"


def _ref(con, today, cfg):
    """ЛЕГАСИ (30.10): поэлементный эталон — прибыль ОДНОЙ сделки ₽/лот.

    Правило давно счётовое (см. _daily_ref); функция оставлена для сверки:
    именно она давала «50 053 ₽/лот», несравнимые с дневной метрикой графика.
    

    Окно: lookback_days дней до сегодняшнего дня; lookback_days <= 0 — вся история.


    Возвращает {'ref': float, 'n_rows': int, 'n_days': int, 'last_day': str}
    или None, если истории нет (первый день работы сэмплера).
    """
    from_day = _window_start(today, cfg.lookback_days)
    try:
        rows = con.execute(
            "SELECT peak_per_lot FROM position_peak "
            "WHERE day >= ? AND day < ? AND peak_per_lot IS NOT NULL "
            "AND COALESCE(volume, 0) >= ?",
            (from_day, today, float(cfg.min_ref_volume))).fetchall()
        meta = con.execute(
            "SELECT COUNT(DISTINCT day) AS n_days, MAX(day) AS last_day "
            "FROM position_peak WHERE day >= ? AND day < ? AND peak_per_lot IS NOT NULL",
            (from_day, today)).fetchone()
    except Exception:
        return None  # старая БД без position_peak — эталона нет
    values = [float(r['peak_per_lot']) for r in rows if r['peak_per_lot'] is not None]
    if not values:
        return None
    return {'ref': _pct(values, cfg.ref_quantile),
            'n_rows': len(values),
            'n_days': int((meta['n_days'] if meta else 0) or 0),
            'last_day': (meta['last_day'] if meta else None)}


# Кэш «изначальных объёмов» срезанных позиций: гейт входа зовётся на каждом
# проходе проверки сигналов, поэтому БД читаем не чаще, чем раз в _TRIM_VOL_TTL.
_TRIM_VOL_CACHE = {'ts': -1e12, 'path': None, 'data': {}}
_TRIM_VOL_TTL = 30.0


def trimmed_volumes(path=None, ttl=None):
    """{position_id: последняя РЕАЛЬНАЯ резка} — для расчёта квот и плана.

    Зачем: после трима в MT5 остаётся keep_volume (0.01), и риск позиции падает
    в volume_before/0.01 раз — свободный бюджет тут же выдаётся (категория,
    группа, счёт), робот набирает объём заново и следующий проход через 60 с
    режет его снова. Поэтому квоты считаем по ИЗНАЧАЛЬНОМУ объёму, пока позиция
    торгует: бюджет освободится сам, когда её закроет SL/TP (тикет ушёл из MT5).
    Возвращает {position_id: {'volume_before', 'volume_left', 'symbol', 'magic',
    'day', 'ts'}}. Любая ошибка/нет БД = {} (квоты по живым объёмам).
    """
    try:
        import trades_db
        _ttl = _TRIM_VOL_TTL if ttl is None else float(ttl)
        _now = datetime.datetime.now().timestamp()
        if (_TRIM_VOL_CACHE['path'] == path
                and (_now - float(_TRIM_VOL_CACHE['ts'])) < _ttl):
            return _TRIM_VOL_CACHE['data']
        con = trades_db.connect(path)
        _ensure_table(con)
        rows = con.execute(
            "SELECT ts, day, position_id, symbol, magic, volume_before, "
            "volume_left FROM peak_trim WHERE mode = 'real' ORDER BY ts").fetchall()
        out = {}
        for r in rows:
            try:
                pid = int(r['position_id'] or 0)
            except (TypeError, ValueError):
                continue
            if pid <= 0:
                continue
            out[pid] = {'volume_before': float(r['volume_before'] or 0.0),
                        'volume_left': float(r['volume_left'] or 0.0),
                        'symbol': str(r['symbol'] or ''),
                        'magic': int(r['magic'] or 0),
                        'day': str(r['day'] or ''),
                        'ts': int(r['ts'] or 0)}
        _TRIM_VOL_CACHE.update({'ts': _now, 'path': path, 'data': out})
        return out
    except Exception:
        return {}


def effective_volume(position_id, volume, trimmed=None):
    """Объём для расчёта квот: ИЗНАЧАЛЬНЫЙ (до трима), если позицию уже резали.

    SL остатка при частичном закрытии не меняется, поэтому
    effective_volume × риск_на_лот воспроизводит риск позиции ДО трима.
    """
    try:
        t = (trimmed or {}).get(int(position_id or 0))
        vol = float(volume or 0.0)
        if not t:
            return vol
        return max(vol, float(t.get('volume_before') or 0.0))
    except (TypeError, ValueError):
        return float(volume or 0.0)


def _already_trimmed(con, day, login, position_id):
    """Была ли уже РЕАЛЬНАЯ фиксация по этой позиции в этот день."""
    try:
        row = con.execute(
            "SELECT 1 FROM peak_trim WHERE day = ? AND account_login = ? "
            "AND position_id = ? AND mode = 'real' LIMIT 1",
            (day, login, position_id)).fetchone()
    except Exception:
        return False
    return row is not None


def _max_ratio(con, day, login, position_id):
    """Максимальный уже записанный ratio по этой позиции за день (анти-спам).

    Сэмплер тикает каждые ~5 мин: без этой отсечки одна и та же позиция писала бы
    строку в peak_trim 288 раз в сутки. Логируем только НОВЫЕ ступени (шаг 10%
    эталона), поэтому в таблице появляется «лестница» роста удельной прибыли.
    """
    try:
        row = con.execute(
            "SELECT MAX(ref_pct) AS mx FROM peak_trim "
            "WHERE day = ? AND account_login = ? AND position_id = ?",
            (day, login, position_id)).fetchone()
    except Exception:
        return -1.0
    if row is None or row['mx'] is None:
        return -1.0
    return float(row['mx'])


def _close_volume(info, volume, keep_volume):
    """Сколько закрыть, чтобы осталось ровно keep_volume (с учётом шага лота)."""
    vol = float(volume or 0.0)
    keep = float(keep_volume or 0.0)
    want = vol - keep
    step = float(getattr(info, 'volume_step', 0.01) or 0.01) if info is not None else 0.01
    vmin = float(getattr(info, 'volume_min', 0.01) or 0.01) if info is not None else 0.01
    vmax = float(getattr(info, 'volume_max', 0.0) or 0.0) if info is not None else 0.0
    if want <= 0 or step <= 0:
        return 0.0
    out = round(int(round(want / step)) * step, 8)
    if out > want + 1e-9:           # не уходим ниже «оставить keep_volume»
        out = round(out - step, 8)
    if out < vmin:
        return 0.0
    if vmax > 0 and out > vmax:
        out = vmax
    return out


def _send_close(mt5, pos, volume, info, tick):
    """Закрыть ЧАСТЬ позиции встречной сделкой по тикету. Возвращает (result, comment).

    Используется только при cfg.enabled=True (сейчас режим оценки — не вызывается).
    """
    if tick is None:
        return None, 'no_tick'
    is_buy = int(getattr(pos, 'type', 0) or 0) == int(getattr(mt5, 'POSITION_TYPE_BUY', 0))
    price = float(tick.bid if is_buy else tick.ask)
    filling = int(getattr(mt5, 'ORDER_FILLING_RETURN', 0) or 0)
    fm = int(getattr(info, 'filling_mode', 0) or 0) if info is not None else 0
    if fm & 1:
        filling = mt5.ORDER_FILLING_FOK
    elif fm & 2:
        filling = mt5.ORDER_FILLING_IOC
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'position': int(getattr(pos, 'ticket', 0) or 0),
        'symbol': getattr(pos, 'symbol', '') or '',
        'volume': float(volume),
        'type': mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
        'price': price,
        'deviation': 30,
        'magic': int(getattr(pos, 'magic', 0) or 0),
        'comment': 'peak-trim',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': filling,
    }
    res = mt5.order_send(req)
    if res is None:
        return None, 'no_result'
    return res, f"{getattr(res, 'retcode', '')} {getattr(res, 'comment', '')}".strip()


# Анти-спам для счётового лога: последняя записанная ступень (10% эталона)
_ACCT_LOG = {'day': None, 'band': -1.0}

# Анти-спам ошибок прохода. Раньше сбой печатался только при verbose=True, а
# main.py зовёт scan_and_trim(verbose=False): NameError в _today_per_lot молчал
# с 03.11 по 10.11. Теперь ошибку печатаем ВСЕГДА, но не чаще, чем раз в
# _ERR_EVERY_SEC секунд на одинаковый текст.
_ERR_LOG = {'msg': '', 'ts': 0.0}
_ERR_EVERY_SEC = 600


def _flows_map():
    """Внешние деньги (пополнения/выводы) по дням: {day: [(ts_true, amount)]}.

    Тот же смысл, что в risk_equity_block._flows_df: 'cutoff'/'bootstrap' — это
    входящий остаток периода учёта, а не движение денег внутри суток, поэтому он
    не вычитается. У 'deals' ts — серверное время «под видом UTC» (+3 ч),
    у 'reconcile'/'manual' — обычный epoch.
    """
    out = {}
    try:
        import cashflow
        # Только реальные движения (source='deals'): 'reconcile' — синтетика сверки,
        # дублировавшая пополнения; 'cutoff'/'bootstrap' — входящий остаток.
        rows = cashflow.ops_list(limit=5000, sources=('deals',))
    except Exception:
        return out
    for row in rows:
        try:
            _ts = int(row[0])
            _amt = float(row[1])
            _src = str(row[3] or '')
        except (TypeError, ValueError, IndexError):
            continue
        if _src in ('cutoff', 'bootstrap') or _amt == 0:
            continue
        _shift = 0 if _src in ('reconcile', 'manual') else SRV_OFFSET_H * 3600
        _ts_true = _ts - _shift
        out.setdefault(_day_of_ts(_ts_true), []).append((_ts_true, _amt))
    for _v in out.values():
        _v.sort()
    return out


def _day_of_ts(ts):
    """Серверная дата 'YYYY-MM-DD' для истинного epoch."""
    try:
        ts = int(ts)
        if ts <= 0:
            return None
        return datetime.datetime.fromtimestamp(
            ts + SRV_OFFSET_H * 3600, datetime.timezone.utc).strftime('%Y-%m-%d')
    except (ValueError, OSError, OverflowError):
        return None


def _day_start_ts(day_str):
    """Истинный epoch начала серверных суток day_str (00:00 UTC+3)."""
    _d = datetime.date.fromisoformat(day_str)
    return (_d - datetime.date(1970, 1, 1)).days * 86400 - SRV_OFFSET_H * 3600


def _realized_by_day(from_day, login):
    """Реализованный P&L сделок по серверным дням: {день: [(ts, cum_net), ...]}.

    Потенциал дня = реализованный P&L сделок этого дня + плавающая открытых
    позиций. Пополнений и выводов в формуле нет: это не сделки. Берутся только
    торговые сделки deal_type IN (0,1), поэтому балансовые операции (пополнение,
    снятие, кредит) в расчёт попасть не могут.
    net = profit + commission + swap + fee — комиссии и свопы тоже деньги счёта.
    deals.time — серверное время «под видом UTC»: ts = time − SRV_OFFSET_H.
    Список отсортирован по времени, второе поле — накопленная сумма за день.
    """
    out = {}
    try:
        _con = trades_db.connect(readonly=True)
        _srv0 = _day_start_ts(from_day) + SRV_OFFSET_H * 3600
        where = "deal_type IN (0, 1) AND time >= ?"
        params = [_srv0]
        if login:
            where += " AND account_login = ?"
            params.append(int(login))
        rows = _con.execute(
            "SELECT time, profit, commission, swap, fee FROM deals "
            f"WHERE {where} ORDER BY time", tuple(params)).fetchall()
        _con.close()
    except Exception:
        return out
    run = {}
    for r in rows:
        try:
            _ts = int(r['time']) - SRV_OFFSET_H * 3600
            _net = (float(r['profit'] or 0.0) + float(r['commission'] or 0.0)
                    + float(r['swap'] or 0.0) + float(r['fee'] or 0.0))
        except (TypeError, ValueError):
            continue
        day = _day_of_ts(_ts)
        if day is None:
            continue
        run[day] = run.get(day, 0.0) + _net
        out.setdefault(day, []).append((_ts, run[day]))
    return out


def _realized_at(series, day, ts):
    """Реализованный P&L сделок дня к моменту ts (истинный epoch), ₽."""
    pts = (series or {}).get(day)
    if not pts:
        return 0.0
    ts = int(ts)
    val = 0.0
    for _ts, _cum in pts:
        if _ts > ts:
            break
        val = _cum
    return val


def _daily_per_lot(con, login, from_day):
    """Удельная прибыль по дням: {day: ₽/лот}.

    Считается РОВНО как график Risk (risk_equity_block._daily): per_lot дня =
    max по замерам дня от (потенциал дня / ПЛАНОВЫЙ объём дня), где плановый
    объём = максимум объёма книги за сутки (только замеры с объёмом > 0).
    Почему плановый, а не «объём этого замера»: после трима книга падает до
    0.01 × N, потенциал дня остаётся — на объёме замера удельная задирается в
    plan_vol/остаток раз (×10-20), и медиана следующих дней уезжает вверх.
    Удельная за день = пик потенциала дня / plan_vol дня.


    Потенциал дня = реализованный P&L сделок этого дня (по времени закрытия) плюс
    плавающая открытых позиций; пополнений и выводов в формуле нет — это не сделки.
    Выходные дни пропускаем.
    (то есть реализованное за день + текущий floating). Выходные пропускаем.
    """
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(equity_samples)")}
    except Exception:
        return {}
    if not cols or 'floating_volume' not in cols:
        return {}      # старые базы без объёма: счётовую удельную не посчитать
    where = "ts >= ?"
    params = [_day_start_ts(from_day)]
    if 'account_login' in cols and login:
        where += " AND (account_login IS NULL OR account_login = ?)"
        params.append(int(login))
    try:
        rows = con.execute(
            "SELECT ts, balance, floating_total, floating_volume FROM equity_samples "
            f"WHERE {where} ORDER BY ts", tuple(params)).fetchall()
    except Exception:
        return {}
    realized = _realized_by_day(from_day, login)
    days = {}
    for r in rows:
        try:
            ts = int(r['ts'])
            bal = float(r['balance'])
            fl = float(r['floating_total'])
            vol = float(r['floating_volume']) if r['floating_volume'] is not None else 0.0
        except (TypeError, ValueError):
            continue
        day = _day_of_ts(ts)
        if day is None:
            continue  # пропускаем невалидные timestamp
        d = days.get(day)
        if d is None:
            d = {'pot': None, 'vol': 0.0}
            days[day] = d
        # Реализованный P&L сделок этого дня к моменту ts: только деньги сделок,
        _real = _realized_at(realized, day, ts)
        # пополнений и выводов здесь нет — это не сделки (deal_type IN (0,1)).
        # Баланс на 00:00 и внешние деньги в формуле не участвуют:
        # потенциал = реализованное по сделкам + плавающая открытых позиций.
        # Знак потенциала — знак торгового дня; выходные ниже пропускаем.
        # (Так ушёл фиктивный пик 02.11: вывод денег «прибавлялся» к потенциалу,
        #  потому что вычитался из equity со знаком минус.) Выходные — ниже.
        if not (vol > 0):
            continue                 # без объёма удельную не посчитать
        # Копим пик потенциала дня и максимум объёма книги: удельная считается
        # в конце цикла как pot / plan_vol — знаменатель ОДИН на день, поэтому
        # резка/закрытие позиций не задирает ₽/лот.
        d['vol'] = max(float(d['vol']), vol)
        _pot = _real + fl
        if d['pot'] is None or _pot > d['pot']:
            d['pot'] = _pot
    out = {}
    for day, d in days.items():
        if d['pot'] is None or not (float(d['vol']) > 0):
            continue
        try:
            if datetime.date.fromisoformat(day).weekday() >= 5:
                continue             # выходные в графике не участвуют
        except ValueError:
            continue
        out[day] = float(d['pot']) / float(d['vol'])
    return out


def _daily_ref(con, today, cfg, login):
    """Эталон ₽/лот — агрегат удельной прибыли ДНЯ за историю до сегодняшнего.

    Окно: cfg.lookback_days дней до сегодня; 0 — вся история с начала работы
    робота (реально с 16.10 — с первого замера equity_samples).
    Агрегат задаёт cfg.ref_quantile: 0.50 — МЕДИАНА дневных пиков ₽/лот (то же
    число, что лейбл дэша «Медиана на 1 лот»; действующий режим с 30.10),
    1.00 — максимум дня (прежний режим «99% пика»).
    """
    from_day = _window_start(today, cfg.lookback_days)
    series = _daily_per_lot(con, login, from_day)
    vals = {d: v for d, v in series.items() if d < today}
    if not vals:
        return None
    best_day = max(vals, key=lambda k: vals[k])
    return {'ref': _pct(list(vals.values()), cfg.ref_quantile),
            'best': float(vals[best_day]),
            'best_day': best_day,
            'n_days': len(vals),
            'last_day': max(vals)}


def _plan_from_state():
    """Σ лотов плана из journals/active_state.json: (объём, дата сборки плана).

    Файл собирает ночной реранк (~00:49), расклад — на текущие сутки, поэтому
    план известен с утра и в течение дня не меняется. Кэш PLAN_CACHE_SEC, чтобы
    не читать файл на каждом замере. Возвращает (0.0, '') — плана нет, файл
    битый, план пуст или старше PLAN_MAX_AGE_H часов (тогда работает фолбэк
    в _plan_volume: максимум фактической книги за сутки).
    """
    now = datetime.datetime.now()
    if _PLAN_CACHE['ts'] and (now.timestamp() - _PLAN_CACHE['ts']) < PLAN_CACHE_SEC:
        return float(_PLAN_CACHE['vol']), str(_PLAN_CACHE['updated'])
    vol, updated = 0.0, ''
    try:
        with open(PLAN_STATE_PATH, 'r', encoding='utf-8') as fh:
            state = json.load(fh)
        for item in (state.get('strategies') or []):
            try:
                vol += float(item.get('lot') or 0.0)
            except (TypeError, ValueError):
                continue
        updated = str(state.get('updated') or '')
        if updated:
            try:
                _age_h = ((now - datetime.datetime.fromisoformat(updated))
                          .total_seconds() / 3600.0)
            except ValueError:
                _age_h = 0.0
            if _age_h > PLAN_MAX_AGE_H:
                vol = 0.0      # план протух — реранк не прошёл, берём фолбэк
    except (OSError, ValueError, TypeError):
        vol, updated = 0.0, ''
    _PLAN_CACHE.update({'ts': now.timestamp(), 'vol': vol, 'updated': updated})
    return float(vol), str(updated)


def _plan_volume(con, today, login, cur_vol):
    """Плановый объём дня (лот) — Σ лотов плана из journals/active_state.json.

    План собирает ночной реранк и в течение суток НЕ меняется: порог трима в
    рублях (pct × эталон × plan_vol) один на день и не «догоняет» разросшуюся
    книгу, как было с максимумом фактического объёма за сутки.
    Знаменатель удельной тоже один на день: закрытие пачки сделок не задирает
    ₽/лот. Фолбэк (плана нет / он битый / старше PLAN_MAX_AGE_H часов) — прежнее
    поведение: максимум книги из equity_samples плюс текущий объём.
    Уход текущей книги от плана проверяем допуском cfg.volume_tolerance_pct.
    """

    plan, _plan_upd = _plan_from_state()
    if plan > 0:
        return plan
    # Фолбэк: плана нет или он протух — максимум фактической книги за сутки
    # (прежнее поведение до 05.11.2026: порог рос вместе с книгой)
    # (источник плана, кэш и срок годности — в _plan_from_state).
    # плана нет — считаем по фактической книге; порог тогда снова «плывёт».
    best = float(cur_vol or 0.0)
    try:
        row = con.execute(
            "SELECT MAX(floating_volume) AS mv FROM equity_samples "
            "WHERE ts >= ? AND (account_login IS NULL OR account_login = ?)",
            (_day_start_ts(today), int(login))).fetchone()
        if row is not None and row['mv'] is not None:
            best = max(best, float(row['mv']))
    except Exception:
        pass
    return best


def _today_per_lot(con, acc, positions, today, login, tolerance=0.20):
    """Текущая удельная прибыль дня: потенциал дня / ПЛАНОВЫЙ объём дня.

    Плановый объём дня (_plan_volume) — Σ лотов из journals/active_state.json:
    он фиксирован на сутки, поэтому удельная не задирается, а порог в рублях
    не «догоняет» книгу, разросшуюся за день (фолбэк — максимум книги за сутки).
    Допуск tolerance — насколько текущий объём может уйти от плана (±20%);
    vol_dev/in_tol возвращаем, чтобы лог и дэш показали уход объёма от плана.
    День считается по серверному времени (UTC+3), как и дни эталона.

    Потенциал дня = реализованный P&L сделок сегодняшних суток по времени
    закрытия плюс плавающая открытых позиций. Пополнений и выводов в формуле
    нет: это не сделки (deal_type IN (0,1)). См. _realized_by_day.
    """
    # Баланс на счету на начало суток больше не нужен: потенциал не от баланса.
    _real = _realized_at(_realized_by_day(today, login), today, int(datetime.datetime.now().timestamp()))
    # Плавающая — «живьём» из счёта: equity минус balance.
    _floating = (float(getattr(acc, 'equity', 0.0) or 0.0)
                 - float(getattr(acc, 'balance', 0.0) or 0.0))
    vol = 0.0
    for p in positions:
        vol += float(getattr(p, 'volume', 0.0) or 0.0)
    potential = _real + _floating
    # Прежняя формула: equity − баланс_на_00:00 − ext, где ext — накопленные
    # пополнения/выводы дня. При выводе ext < 0 «минус на минус» прибавлял
    # сумму к потенциалу — отсюда фиктивные пики 02.11.2026 (195 000 ₽).
    # Теперь: potential = реализованные сделки дня + floating открытых позиций.
    # Сделки — из trades_db (deal_type IN (0,1)): пополнение сделкой не является.
    # Если ингест сделок отстал, останется только плавающая — это честнее,
    # чем подмешивать баланс счёта и внешние деньги.
    # Ниже — знаменатель удельной (плановый объём дня), код не менялся.
    # Та же формула — в risk_equity_block._daily (оба графика вкладки Risk).
    # Проверка: python peak_trim.py --live печатает текущий P&L и порог.
    # Ключи balance_start / ext из возвращаемого словаря убраны (03.11.2026):
    # potential и per_lot остались теми же ключами — трим читает их как раньше.
    # Знаменатель удельной — ПЛАНОВЫЙ объём дня, не остаток книги: иначе
    # закрытие пары сделок уменьшает объём, ₽/лот растёт и трим врёт.
    # Источник знаменателя: план из active_state.json, иначе фолбэк на книгу.
    _plan_state, _plan_upd = _plan_from_state()
    plan_vol = _plan_volume(con, today, login, vol)
    denom = plan_vol if plan_vol > 0 else vol
    vol_dev = ((vol - plan_vol) / plan_vol) if plan_vol > 0 else 0.0
    return {'potential': potential, 'vol': vol, 'plan_vol': plan_vol,
            'plan_src': ('план' if _plan_state > 0 else 'книга'),
            'plan_updated': _plan_upd,
            'vol_dev': vol_dev, 'in_tol': abs(vol_dev) <= float(tolerance),
            'realized': _real,
            'floating': _floating, 'per_lot': (potential / denom if denom > 0 else None),
            'per_lot_now': (potential / vol if vol > 0 else None)}


def _log_band(today, band):
    """Анти-спам счётового лога: пишем, только если выросла ступень 10% эталона."""
    if _ACCT_LOG.get('day') != today:
        _ACCT_LOG['day'] = today
        _ACCT_LOG['band'] = -1.0
    if band <= float(_ACCT_LOG.get('band', -1.0)):
        return False
    _ACCT_LOG['band'] = band
    return True


def scan_and_trim(cfg=None, path=None, verbose=True):
    """Один проход по открытым позициям. Возвращает число сработавших триггеров.

    Режим оценки: закрытий нет, пока cfg.enabled=False. Вызывать после
    sample_positions(), чтобы эталон и текущие пики были свежими.
    """
    cfg = cfg or PeakTrimParams()
    if not cfg.enabled and not cfg.shadow:
        return 0
    try:
        import MetaTrader5 as mt5
        import trades_db
    except Exception as exc:
        if verbose:
            print(f"  [TRIM] пропуск: {exc!r}", flush=True)
        return 0
    if not trades_db._ensure_mt5(verbose=False):
        if verbose:
            print("  [TRIM] нет соединения с MT5 — проверка пропущена", flush=True)
        return 0
    try:
        acc = mt5.account_info()
        if acc is None:
            return 0
        positions = mt5.positions_get() or []
        if not positions:
            return 0
        now = datetime.datetime.now()
        now_ts = int(now.timestamp())
        today = now.strftime('%Y-%m-%d')
        login = int(acc.login)
        registry = trades_db.load_registry()

        con = trades_db.connect(path)
        try:
            _ensure_table(con)
            ref = _daily_ref(con, today, cfg, login)
            if not ref or float(ref['ref']) <= 0:
                if verbose:
                    print("  [TRIM] эталона пока нет: в equity_samples нет дней до "
                          "сегодняшнего дня — правило не оцениваем", flush=True)
                return 0

            ref_val = float(ref['ref'])
            if ref_val < float(cfg.min_ref_per_lot):
                if verbose:
                    print(f"  [TRIM] эталон ({_ref_label(cfg)}) слишком мал ({_space(ref_val)} ₽/лот < "
                          f"{_space(cfg.min_ref_per_lot)}) — правило не оцениваем",
                          flush=True)
                return 0
            # Объём в правиле — ПЛАНОВЫЙ объём дня из active_state.json (Σ лотов),
            # допуск отклонения текущего объёма от плана — volume_tolerance_pct.
            _tol = float(getattr(cfg, 'volume_tolerance_pct', 0.20))
            cur = _today_per_lot(con, acc, positions, today, login, _tol)
            _per_now = cur.get('per_lot')
            if _per_now is None or float(cur.get('plan_vol') or 0) <= 0:
                if verbose:
                    print("  [TRIM] плановый объём дня 0 — удельную дня не считаем", flush=True)
                return 0
            _acct_ratio = float(_per_now) / ref_val
            # Трейлинг от пика дня (решение 10.11.2026): активация на trail_act
            # эталонах, срез при откате trail_pct от пика удельной за день.
            # Пик живёт в атрибуте функции и сбрасывается со сменой дня.
            _act = float(getattr(cfg, 'trail_act', 2.0))
            _tr = float(getattr(cfg, 'trail_pct', 0.25))
            _st = getattr(scan_and_trim, '_trail', None)
            if not (_st and _st[0] == today):
                _st = [today, 0.0]               # новый день — пик с нуля
            if _acct_ratio >= _act:              # трейл активен — копим пик дня
                _st[1] = max(_st[1], _acct_ratio)
            _acct_hit = bool(_acct_ratio >= _act
                             and _acct_ratio <= _st[1] * (1.0 - _tr))
            scan_and_trim._trail = _st           # живёт в памяти процесса, ~1 день
            # Объём ушёл от планового больше допуска (закрылась пачка сделок или
            # книга разрослась): удельную всё равно считаем по плановому объёму,
            # но пишем предупреждение — одна строка на ступень отклонения.
            if not bool(cur.get('in_tol', True)) and _log_band(
                    today, abs(float(cur.get('vol_dev') or 0.0))):
                print(f"  [TRIM] объём вне допуска: книга {float(cur.get('vol') or 0):.2f} лот "
                      f"vs плановых {float(cur.get('plan_vol') or 0):.2f} лот "
                      f"({float(cur.get('vol_dev') or 0) * 100:+.0f}%, допуск "
                      f"±{_tol * 100:.0f}%) — удельную считаем по плановому объёму",
                      flush=True)

            # СУММАРНАЯ картина
            if verbose:
                total_profit = sum(
                    float(getattr(p, 'profit', 0) or 0) + float(getattr(p, 'swap', 0) or 0)
                    for p in positions
                )
                total_vol = sum(float(getattr(p, 'volume', 0) or 0) for p in positions)
                total_per_lot = total_profit / total_vol if total_vol > 0 else 0

                print(f"  [TRIM] СУММАРНО:", flush=True)
                print(f"  [TRIM]   Потенциал: {total_profit:+,.0f} ₽ | Объём: {total_vol:.2f} лот",
                      flush=True)
                print(f"  [TRIM]   Удельная: {_space(total_per_lot)} ₽/лот",
                      flush=True)
                print(f"  [TRIM]   Объём: {float(cur.get('vol') or 0):.2f} из плановых "
                      f"{float(cur.get('plan_vol') or 0):.2f} лот "
                      f"[{cur.get('plan_src') or '?'}] "
                      f"({float(cur.get('vol_dev') or 0) * 100:+.0f}%, "
                      f"допуск ±{_tol * 100:.0f}%)", flush=True)
                print(f"  [TRIM]   Эталон: {_space(ref_val)} ₽/лот ({_ref_label(cfg)})",
                      flush=True)
                _plan_v = float(cur.get('plan_vol') or 0)
                _peak_txt = (f"{_st[1] * 100:.0f}% эталона, срез ниже "
                             f"{_st[1] * (1.0 - _tr) * 100:.0f}%" if _st[1] > 0
                             else 'ещё не активирован')
                print(f"  [TRIM]   Активация: {ref_val * _act * _plan_v:,.0f} ₽ ({_act:g}× эталона × план {_plan_v:.2f} лот) "
                      f"| трейл {_tr:.0%} | пик дня: {_peak_txt}",
                      flush=True)
                print(f"  [TRIM]   Выполнение: {_acct_ratio * 100:.0f}% {'→ РЕЖЕМ' if _acct_hit else ''}",
                      flush=True)

            # Режем ВСЕ позиции счёта: блок стоит на уровне функции, не под
            # `if verbose` — иначе при verbose=False (вызов из main.py) закрытий
            # не было бы вовсе, а `triggers` остался бы неопределённым.
            triggers = 0
            if _acct_hit:
                    triggers = 0
                    for p in positions:
                        try:
                            ticket = (int(getattr(p, 'ticket', 0) or 0)
                                      or int(getattr(p, 'position_id', 0) or 0))
                            if not ticket:
                                continue
                            magic = int(getattr(p, 'magic', 0) or 0)
                            if not (_MIN_MAGIC <= magic <= _MAX_MAGIC):
                                continue
                            vol = float(getattr(p, 'volume', 0.0) or 0.0)
                            if vol <= float(cfg.keep_volume):
                                continue
                            symbol = getattr(p, 'symbol', '') or ''
                            category = trades_db._category_of(symbol, magic, registry)
                            info = mt5.symbol_info(symbol)
                            close_vol = _close_volume(info, vol, cfg.keep_volume)
                            if close_vol <= 0:
                                continue      # резать нечего: объём <= keep или шаг лота
                            price = float(getattr(p, 'price_current', 0.0) or 0.0)
                            mode = 'shadow'
                            retcode = None
                            rcomment = ''
                            if cfg.enabled:
                                tick = mt5.symbol_info_tick(symbol)
                                res, rcomment = _send_close(mt5, p, close_vol, info, tick)
                                retcode = int(getattr(res, 'retcode', 0) or 0) if res is not None else None
                                ok_codes = (int(getattr(mt5, 'TRADE_RETCODE_DONE', 0)),
                                            int(getattr(mt5, 'TRADE_RETCODE_DONE_PARTIAL', 0)))
                                mode = 'real' if retcode in ok_codes else 'failed'
                                if mode == 'real':
                                    triggers += 1
                            else:
                                triggers += 1

                            rec = registry.get(magic) or {}
                            con.execute(
                                "INSERT INTO peak_trim (ts, day, account_login, position_id, "
                                "symbol, family, category, magic, volume_before, volume_closed, "
                                "volume_left, price, float_money, float_per_lot, ref_per_lot, "
                                "ref_pct, ref_scope, ref_last_day, mode, retcode, result_comment) "
                                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (now_ts, today, login, ticket, symbol, rec.get('family'),
                                 category, magic, vol, close_vol,
                                 round(vol - close_vol, 8), price,
                                 round(float(getattr(p, 'profit', 0) or 0)
                                       + float(getattr(p, 'swap', 0) or 0), 2),
                                 round((float(getattr(p, 'profit', 0) or 0)
                                        + float(getattr(p, 'swap', 0) or 0)) / vol, 2)
                                 if vol > 0 else 0,
                                 round(ref_val, 2),
                                 round(_acct_ratio, 4), 'account_day', ref['last_day'],
                                 mode, retcode, rcomment))

                            _left = round(vol - close_vol, 2)
                            print(f"  [TRIM] → {symbol}: {vol:.2f} → закрыть {close_vol:.2f}, оставить {_left:.2f}",
                                  flush=True)
                        except Exception as pos_err:
                            if verbose:
                                print(f"  [TRIM] позиция #{getattr(p, 'ticket', '?')}: {pos_err!r}",
                                      flush=True)
                            continue

            con.commit()
            return triggers

            con.commit()
            return triggers
        finally:
            con.close()
    except Exception as exc:
        # 10.11.2026: сбой печатаем ВСЕГДА — раньше он тонул, потому что main.py
        # зовёт scan_and_trim(verbose=False), а печать была под `if verbose`.
        # Повторы гасит _ERR_LOG (не чаще раза в _ERR_EVERY_SEC на тот же текст).
        _emsg = repr(exc)
        _ets = datetime.datetime.now().timestamp()
        if (_ERR_LOG.get('msg') != _emsg
                or (_ets - float(_ERR_LOG.get('ts') or 0.0)) > _ERR_EVERY_SEC):
            _ERR_LOG.update({'msg': _emsg, 'ts': _ets})
            print(f"  [TRIM] проверка не выполнена: {_emsg}", flush=True)
            
            
            
                    
                
                
        return 0


def evaluate(cfg=None, path=None, verbose=True, thresholds=_EVAL_THRESHOLDS):
    """Оценка правила на уже накопленной истории position_peak.

    Для каждого дня берём эталон p90 по окну ДО этого дня и смотрим, у скольких
    сделок их ЗАСЕЧЁННЫЙ пик (peak_per_lot) дотянул до 70/75/80/85/90% эталона.
    Это верхняя оценка частоты срабатывания: реальный триггер сработал бы не
    позже момента, когда сделка дошла до своего пика.
    """
    cfg = cfg or PeakTrimParams()
    try:
        import trades_db
    except Exception as exc:
        print(f"  [TRIM] оценка невозможна: {exc!r}", flush=True)
        return None
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    from_day = _window_start(today, int(cfg.lookback_days) * 2)
    con = trades_db.connect(path, readonly=True)
    try:
        try:
            rows = con.execute(
                "SELECT day, position_id, peak_per_lot FROM position_peak "
                "WHERE day >= ? AND day <= ? AND peak_per_lot IS NOT NULL "
                "ORDER BY day", (from_day, today)).fetchall()
        except Exception as exc:
            print(f"  [TRIM] position_peak недоступен: {exc!r}", flush=True)
            return None
    finally:
        con.close()

    by_day = {}
    for r in rows:
        by_day.setdefault(r['day'], []).append(float(r['peak_per_lot']))
    if not by_day:
        print("  [TRIM] истории пока нет — оценивать нечего", flush=True)
        return None

    days = sorted(by_day)
    q = float(cfg.ref_quantile)
    head = ''.join(f"{int(t * 100):>7}%" for t in thresholds)
    if verbose:
        print(f"  [TRIM] оценка правила (эталон = p{q * 100:.0f} по окну "
              f"{_win_label(cfg)} ДО дня): доля сделок, чей пик ₽/лот дотянул "
              f"до порога", flush=True)
        print(f"    {'день':<12}{'эталон ₽/лот':>14}{'сделок':>8}{head}", flush=True)

    total = {t: 0 for t in thresholds}
    total_n = 0
    for day in days:
        window = []
        for d in days:
            if _window_start(day, int(cfg.lookback_days)) <= d < day:
                window.extend(by_day[d])
        ref = _pct(window, q)
        vals = by_day[day]
        total_n += len(vals)
        cells = ''
        for t in thresholds:
            if ref > 0:
                n_hit = sum(1 for v in vals if v / ref >= t)
            else:
                n_hit = 0
            total[t] += n_hit
            share = (100.0 * n_hit / len(vals)) if vals else 0.0
            cells += f"{share:>7.0f}%"
        if verbose:
            print(f"    {day:<12}{_space(ref):>14}{len(vals):>8}{cells}", flush=True)

    if total_n and verbose:
        cells = ''.join(f"{100.0 * total[t] / total_n:>7.0f}%" for t in thresholds)
        print(f"    {'ИТОГО':<12}{'':>14}{total_n:>8}{cells}   "
              f"(дней: {len(days)}, окно эталона: {_win_label(cfg)})", flush=True)
    return {'days': len(days), 'positions': total_n,
            'hits': total, 'thresholds': thresholds}


def main():
    """CLI для оценки на живом терминале/базе.

    Примеры:
      python peak_trim.py --eval               # оценка частоты срабатываний
      python peak_trim.py --eval --pct 0.8     # сравнить с другим порогом
      python peak_trim.py --live               # один проход по открытым позициям
    """
    import argparse

    ap = argparse.ArgumentParser(description='Пик-трим: оценка правила фиксации по пику')
    ap.add_argument('--eval', action='store_true', help='оценить правило на истории position_peak')
    ap.add_argument('--live', action='store_true', help='один проход по открытым позициям (shadow)')
    ap.add_argument('--real', action='store_true', help='ВНИМАНИЕ: реально закрывать (по умолчанию нет)')
    ap.add_argument('--pct', type=float, default=None, help='исторический порог от эталона (в решении не участвует)')
    ap.add_argument('--act', type=float, default=None, help='активация трейла, во сколько эталонов (2.0)')
    ap.add_argument('--trail', type=float, default=None, help='срез при откате от пика дня (0.25)')
    ap.add_argument('--keep', type=float, default=None, help='оставить объём (0.01)')
    ap.add_argument('--days', type=int, default=None, help='окно истории эталона, дней')
    ap.add_argument('--quantile', type=float, default=None, help='агрегат эталона (0.90 = p90)')
    ap.add_argument('--db', default=None, help='путь к trades.db (по умолчанию journals/trades.db)')
    args = ap.parse_args()

    base = PeakTrimParams()
    cfg = PeakTrimParams(
        enabled=bool(args.real),
        shadow=True,
        pct=args.pct if args.pct is not None else base.pct,
        trail_act=args.act if args.act is not None else base.trail_act,
        trail_pct=args.trail if args.trail is not None else base.trail_pct,
        keep_volume=args.keep if args.keep is not None else base.keep_volume,
        lookback_days=args.days if args.days is not None else base.lookback_days,
        ref_quantile=args.quantile if args.quantile is not None else base.ref_quantile,
        min_ref_per_lot=base.min_ref_per_lot,
        min_money=base.min_money,
        log_from_pct=base.log_from_pct,
        single_shot=base.single_shot,
    )
    print(f"  [TRIM] режим: {'REAL' if cfg.enabled else 'ОЦЕНКА (без закрытий)'} | "
          f"трейл {cfg.trail_pct:.0%} от пика дня, активация {cfg.trail_act:g}× эталона | "
          f"оставляем {cfg.keep_volume:.2f} лот | "
          f"эталон {_ref_label(cfg)} | "
          f"окно {_win_label(cfg)}", flush=True)
    if args.eval or not args.live:
        evaluate(cfg=cfg, path=args.db)
    if args.live:

        _plan_vol_d, _plan_upd_d = _plan_from_state()
        if _plan_vol_d > 0:
            print(f"  [TRIM] план дня: {_plan_vol_d:.2f} лот "
                  f"(journals/active_state.json, собран {_plan_upd_d})", flush=True)
        else:
            print("  [TRIM] план дня: НЕТ достоверного плана — фолбэк на максимум "
                  "фактической книги за сутки (порог будет расти в течение дня)",
                  flush=True)
        n = scan_and_trim(cfg=cfg, path=args.db)
        print(f"  [TRIM] триггеров: {n}", flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
