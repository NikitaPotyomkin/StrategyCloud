"""Пик-трим: ОЦЕНКА правила «фиксируем по историческому пику удельной прибыли».

Замысел (согласован 26.10):
  сделка идёт внутри дня и по удельной прибыли (₽ на лот) проходит 55к → 75к →
  90к ₽/лот. По истории засечённых пиков есть эталон — p90 удельной прибыли по
  ВСЕМУ пулу сделок (без разреза по категориям). Как только текущая сделка
  перевалила 75% (80%, 85% — подбираем) этого эталона — фиксируем почти всё,
  оставляя 0.01 лот. Остаток продолжает торговаться и ОБНОВЛЯТЬ пики, поэтому
  эталон со временем поднимается сам.

  ПОКА ТОЛЬКО ОЦЕНКА: реальных закрытий нет (PeakTrimParams.enabled=False).
  Модуль считает решения, пишет их в таблицу peak_trim (mode='shadow') и умеет
  показать, как часто правило сработало бы на уже накопленной истории.

Откуда данные:
  trades_db.sample_positions() каждые ~300 с пишет в position_peak 1 строку на
  (день, аккаунт, position_id) с peak_float / peak_per_lot. Именно peak_per_lot
  (₽ на лот) — объёмно-инвариантная величина, поэтому 0.01 и 1.0 лот сравнимы.

Что делает scan_and_trim() (на каждом тике сэмплера):
  1) эталон = p90(peak_per_lot) по всем сделкам за lookback_days ДО сегодня;
  2) по каждой ОТКРЫТОЙ позиции считает текущую удельную прибыль ₽/лот;
  3) ratio = текущая_удельная / эталон; если ratio >= pct — в лог идёт
     `[TRIM] would …` (и событие в peak_trim), реального закрытия нет;
  4) повторно позицию в тот же день не считает (single_shot).

Что делает evaluate() (CLI --eval):
  проходит по истории день за днём, для каждого дня берёт эталон по ПРЕДЫДУЩИМ
  дням и считает, у скольких сделок их ЗАСЕЧЁННЫЙ пик превысил 70/75/80/85/90%
  эталона. Это ответ на «как часто правило вообще срабатывает» — до того, как
  включать его в торги.

Безопасность:
  • enabled=False (по умолчанию) — закрытий нет, только лог и запись решения;
  • трогаем только позиции со «стратегическим» magic (770000..869999);
  • не трогаем объём <= keep_volume и прибыль меньше min_money;
  • эталон считается БЕЗ сегодняшнего дня — нет подглядывания в будущее;
  • ошибка по одной позиции не роняет ни сэмплер, ни торговый цикл.

ВНИМАНИЕ: фиксация по пику не гарантирует лучший выход — цена после закрытия
может уйти и дальше (именно это и измеряет остаток 0.01 лот), а сам пик
засекается с шагом сэмплера (5 мин), поэтому фактический экстремум мог быть выше.
"""

import datetime
import math

from config import PeakTrimParams

# «Стратегические» magic: чужие/ручные сделки не трогаем
_MIN_MAGIC = 770000
_MAX_MAGIC = 869999

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
    ref_scope      TEXT,      -- 'global' (p90 по всему пулу сделок)
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
    """Дата начала окна истории (день_str минус days дней)."""
    return (datetime.date.fromisoformat(day_str)
            - datetime.timedelta(days=int(days))).isoformat()


def _ref(con, today, cfg):
    """Эталон ₽/лот: p90 всех засечённых peak_per_lot за окно ДО сегодняшнего дня.

    Возвращает {'ref': float, 'n_rows': int, 'n_days': int, 'last_day': str}
    или None, если истории нет (первый день работы сэмплера).
    """
    from_day = _window_start(today, cfg.lookback_days)
    try:
        rows = con.execute(
            "SELECT peak_per_lot FROM position_peak "
            "WHERE day >= ? AND day < ? AND peak_per_lot IS NOT NULL",
            (from_day, today)).fetchall()
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
            ref = _ref(con, today, cfg)
            if not ref or float(ref['ref']) <= 0:
                if verbose:
                    print("  [TRIM] эталона пока нет: в position_peak нет истории до "
                          "сегодняшнего дня — правило не оцениваем", flush=True)
                return 0

            ref_val = float(ref['ref'])
            if ref_val < float(cfg.min_ref_per_lot):
                if verbose:
                    print(f"  [TRIM] эталон p90 слишком мал ({_space(ref_val)} ₽/лот < "
                          f"{_space(cfg.min_ref_per_lot)}) — правило не оцениваем",
                          flush=True)
                return 0
            triggers = 0
            for p in positions:
                try:
                    ticket = (int(getattr(p, 'ticket', 0) or 0)
                              or int(getattr(p, 'position_id', 0) or 0))
                    if not ticket:
                        continue
                    magic = int(getattr(p, 'magic', 0) or 0)
                    if not (_MIN_MAGIC <= magic <= _MAX_MAGIC):
                        continue          # ручные/чужие сделки не трогаем
                    vol = float(getattr(p, 'volume', 0.0) or 0.0)
                    if vol <= float(cfg.keep_volume):
                        continue          # уже «остаток» — фиксировать нечего
                    float_money = (float(getattr(p, 'profit', 0.0) or 0.0)
                                   + float(getattr(p, 'swap', 0.0) or 0.0))
                    if float_money < float(cfg.min_money):
                        continue          # копейки не трогаем
                    per_lot = float_money / vol if vol > 0 else 0.0
                    ratio = per_lot / ref_val
                    if ratio < float(cfg.log_from_pct):
                        continue          # далеко от планки — молчим
                    # анти-спам: пишем только НОВУЮ ступень роста (10% эталона),
                    # иначе каждые 5 мин сэмплера появлялась бы ещё одна строка
                    _band = int(ratio * 10) / 10.0
                    if _band <= _max_ratio(con, today, login, ticket):
                        continue
                    hit = ratio >= float(cfg.pct)
                    if hit and cfg.single_shot and _already_trimmed(con, today, login, ticket):
                        continue

                    symbol = getattr(p, 'symbol', '') or ''
                    category = trades_db._category_of(symbol, magic, registry)
                    info = mt5.symbol_info(symbol)
                    close_vol = _close_volume(info, vol, cfg.keep_volume) if hit else 0.0
                    price = float(getattr(p, 'price_current', 0.0) or 0.0)
                    mode = 'shadow'
                    retcode = None
                    rcomment = ''
                    if hit and close_vol <= 0:
                        mode = 'shadow'   # фиксировать нечего (объём <= keep_volume)
                    elif hit and cfg.enabled:
                        tick = mt5.symbol_info_tick(symbol)
                        res, rcomment = _send_close(mt5, p, close_vol, info, tick)
                        retcode = int(getattr(res, 'retcode', 0) or 0) if res is not None else None
                        ok_codes = (int(getattr(mt5, 'TRADE_RETCODE_DONE', 0)),
                                    int(getattr(mt5, 'TRADE_RETCODE_DONE_PARTIAL', 0)))
                        mode = 'real' if retcode in ok_codes else 'failed'
                        if mode == 'real':
                            triggers += 1
                    elif hit:
                        triggers += 1     # оценка: посчитали бы срабатывание

                    rec = registry.get(magic) or {}
                    con.execute(
                        "INSERT INTO peak_trim (ts, day, account_login, position_id, "
                        "symbol, family, category, magic, volume_before, volume_closed, "
                        "volume_left, price, float_money, float_per_lot, ref_per_lot, "
                        "ref_pct, ref_scope, ref_last_day, mode, retcode, result_comment) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (now_ts, today, login, ticket, symbol, rec.get('family'),
                         category, magic, vol, close_vol,
                         round(vol - close_vol, 8), price, round(float_money, 2),
                         round(per_lot, 2), round(ref_val, 2),
                         round(ratio, 4), 'global', ref['last_day'],
                         mode, retcode, rcomment))

                    if verbose:
                        _left = round(vol - close_vol, 2)
                        # деньги отдельной строкой: .replace(...) на склейке
                        # литералов затронул бы и запятую в тексте лога
                        _money = f"{float_money:+,.0f}".replace(',', ' ')
                        if hit:
                            _tag = ('REAL  ' if mode == 'real'
                                    else ('FAILED' if mode == 'failed' else 'would '))
                            print(f"  [TRIM] {_tag} #{ticket} {category}: "
                                  f"{_space(per_lot)} ₽/лот = {ratio * 100:.0f}% эталона p90 "
                                  f"{_space(ref_val)} ({ref['n_days']} дн., {ref['n_rows']} сд.) "
                                  f"→ закрыть {close_vol:.2f}, оставить {_left:.2f} "
                                  f"(сейчас {_money} ₽)"
                                  + (f" [{rcomment}]" if rcomment else ''), flush=True)
                        else:
                            print(f"  [TRIM] почти #{ticket} {category}: "
                                  f"{ratio * 100:.0f}% эталона ({_space(per_lot)} из "
                                  f"{_space(ref_val)} ₽/лот)", flush=True)
                except Exception as pos_err:
                    if verbose:
                        print(f"  [TRIM] позиция #{getattr(p, 'ticket', '?')}: {pos_err!r}",
                              flush=True)
                    continue

            con.commit()
            return triggers
        finally:
            con.close()
    except Exception as exc:
        if verbose:
            print(f"  [TRIM] проверка не выполнена: {exc!r}", flush=True)
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
              f"{cfg.lookback_days} дн. ДО дня): доля сделок, чей пик ₽/лот дотянул "
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
              f"(дней: {len(days)}, окно эталона: {cfg.lookback_days} дн.)", flush=True)
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
    ap.add_argument('--pct', type=float, default=None, help='порог от эталона (0.75)')
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
        keep_volume=args.keep if args.keep is not None else base.keep_volume,
        lookback_days=args.days if args.days is not None else base.lookback_days,
        ref_quantile=args.quantile if args.quantile is not None else base.ref_quantile,
        min_ref_per_lot=base.min_ref_per_lot,
        min_money=base.min_money,
        log_from_pct=base.log_from_pct,
        single_shot=base.single_shot,
    )
    print(f"  [TRIM] режим: {'REAL' if cfg.enabled else 'ОЦЕНКА (без закрытий)'} | "
          f"порог {cfg.pct:.0%} | оставляем {cfg.keep_volume:.2f} лот | "
          f"эталон p{cfg.ref_quantile * 100:.0f} по всем сделкам | "
          f"окно {cfg.lookback_days} дн.", flush=True)
    if args.eval or not args.live:
        evaluate(cfg=cfg, path=args.db)
    if args.live:
        n = scan_and_trim(cfg=cfg, path=args.db)
        print(f"  [TRIM] триггеров: {n}", flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
