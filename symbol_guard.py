"""Защита на уровне СИМВОЛА: дневной стоп по деньгам и cooldown после SL.

Зачем (30.10.2026, XAGUSDrfd): 8 входов за сутки, 4 стопа по ~4 100 ₽.
WilliamsR/Coint перезаходили в лонг по серебру каждые 1–3 часа, пока цена
падала 51.4 → 50.2. Счётный лимит «−3% в день» поймал бы это только на −33k ₽,
а лимит риска на сделку (0.5%) не ограничивает ЧИСЛО сделок по символу.
Отсюда два правила — они не альфа, а тормоз:

  1) symbol_day_loss_pct: реализованный минус по символу за СЕРВЕРНЫЕ сутки
     дошёл до X% баланса → новые входы по символу запрещены до 00:00 сервера;
  2) symbol_sl_cooldown_min: после стопа по символу новые входы по нему
     запрещены N минут — не заходим повторно в тот же нож.

Считаем по истории сделок MT5 (history_deals_get), только свой пул magic
[770000..869999]: ручные и чужие сделки символ не блокируют. Состояние
кэшируется на symbol_guard_refresh_sec, чтобы не дёргать историю на каждой
проверке сигналов.

Время: у сделок MT5 `time` — серверное время «под видом UTC» (UTC+3, та же
конвенция, что в peak_trim._flows_map и cashflow), поэтому серверная дата
сделки = utcfromtimestamp(time), а «сейчас» по серверу = UTC + SRV_OFFSET_H.
"""
import datetime

SRV_OFFSET_H = 3
_MAGIC_MIN = 770000
_MAGIC_MAX = 869999

# Кэш истории сделок: одна сборка на symbol_guard_refresh_sec, а не на бар.
_CACHE = {'ts': 0.0, 'day': None, 'state': {}}
# По какому символу уже сказали «вход заблокирован» (без спама на каждом баре).
_WARNED = set()


def _srv_now():
    """Текущее серверное время как naive datetime (UTC+SRV_OFFSET_H)."""
    return (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            + datetime.timedelta(hours=SRV_OFFSET_H))


def _srv_now_ts():
    """Серверный unix-таймфрейм той же природы, что deal.time (псевдо-UTC)."""
    return int(_srv_now().replace(tzinfo=datetime.timezone.utc).timestamp())


def _deal_day(ts):
    """Серверная дата 'YYYY-MM-DD' по deal.time (серверное время «под видом UTC»)."""
    try:
        return datetime.datetime.fromtimestamp(
            int(ts), datetime.timezone.utc).strftime('%Y-%m-%d')
    except (ValueError, TypeError, OSError, OverflowError):
        return None


def _is_ours(magic):
    try:
        m = int(magic or 0)
    except (TypeError, ValueError):
        return False
    return _MAGIC_MIN <= m <= _MAGIC_MAX


def _is_sl(deal):
    """Сделка закрыта по стопу: reason == DEAL_REASON_SL или комментарий '[sl ...]'."""
    try:
        import MetaTrader5 as _mt5
        if int(getattr(deal, 'reason', -1)) == int(getattr(_mt5, 'DEAL_REASON_SL', 4)):
            return True
    except Exception:
        pass
    return str(getattr(deal, 'comment', '') or '').strip().startswith('[sl')


def _pnl(deal):
    """Деньги сделки: profit + swap + commission + fee (comission у брокера 0)."""
    total = 0.0
    for _f in ('profit', 'swap', 'commission', 'fee'):
        try:
            total += float(getattr(deal, _f, 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def refresh(cfg=None, force=False, days_back=2):
    """Состояние по сегодняшним сделкам: {symbol: {profit, sl_ts, sl_n, n}}.

    profit — реализованный результат дня по символу (только наши magic),
    sl_ts — время последнего стопа (псевдо-UTC epoch), sl_n — сколько стопов.
    Кэш на cfg.symbol_guard_refresh_sec: история MT5 не читается на каждый бар.
    """
    now = _srv_now()
    today = now.strftime('%Y-%m-%d')
    _ttl = float(getattr(cfg, 'symbol_guard_refresh_sec', 60) or 60)
    _now_ts = datetime.datetime.now().timestamp()
    if (not force and _CACHE.get('day') == today
            and (_now_ts - float(_CACHE.get('ts') or 0.0)) < _ttl):
        return _CACHE['state']

    state = {}
    try:
        import MetaTrader5 as mt5
        deals = mt5.history_deals_get(now - datetime.timedelta(days=int(days_back)),
                                      now + datetime.timedelta(hours=6)) or ()
    except Exception as exc:
        # Fail-safe: нет истории — не блокируем (защита не должна гасить торговлю).
        print(f"  [GUARD] история сделок недоступна: {exc!r}", flush=True)
        _CACHE.update({'ts': _now_ts, 'day': today, 'state': state})
        return state

    for d in deals:
        if not _is_ours(getattr(d, 'magic', 0)):
            continue
        if _deal_day(getattr(d, 'time', 0)) != today:
            continue
        symbol = str(getattr(d, 'symbol', '') or '')
        if not symbol:
            continue
        rec = state.setdefault(symbol, {'profit': 0.0, 'sl_ts': 0, 'sl_n': 0, 'n': 0})
        rec['n'] += 1
        try:
            _entry = int(getattr(d, 'entry', -1))
        except (TypeError, ValueError):
            _entry = -1
        if _entry not in (1, 2):
            continue     # IN (открытие) денег не даёт: результат считаем по OUT/INOUT
        rec['profit'] += _pnl(d)
        if _is_sl(d):
            rec['sl_n'] += 1
            try:
                rec['sl_ts'] = max(int(rec['sl_ts']), int(getattr(d, 'time', 0) or 0))
            except (TypeError, ValueError):
                pass

    _CACHE.update({'ts': _now_ts, 'day': today, 'state': state})
    return state


def block_reason(symbol, cfg=None, balance=None):
    """Почему вход по символу запрещён: (blocked, причина). ('', False) — можно."""
    if cfg is None:
        try:
            from config import RiskParams as _RiskParams
            cfg = _RiskParams()
        except Exception:
            return False, ''
    if not bool(getattr(cfg, 'symbol_guard_enabled', True)):
        return False, ''
    symbol = str(symbol or '')
    if not symbol:
        return False, ''
    rec = refresh(cfg).get(symbol)
    if not rec:
        return False, ''
    bal = float(balance or 0.0)
    if bal <= 0:
        try:
            import MetaTrader5 as mt5
            acc = mt5.account_info()
            bal = float(getattr(acc, 'balance', 0.0) or 0.0) if acc is not None else 0.0
        except Exception:
            bal = 0.0

    pct = float(getattr(cfg, 'symbol_day_loss_pct', 1.0) or 0.0)
    limit = bal * pct / 100.0
    if pct > 0 and bal > 0 and float(rec.get('profit') or 0.0) <= -limit:
        return True, (f"дневной стоп по {symbol}: реализовано {rec['profit']:+,.0f} ₽ "
                      f"≤ −{limit:,.0f} ₽ ({pct:.1f}% баланса) — до 00:00 сервера")

    cool = float(getattr(cfg, 'symbol_sl_cooldown_min', 60) or 0.0)
    sl_ts = int(rec.get('sl_ts') or 0)
    if cool > 0 and sl_ts > 0:
        left_min = cool - (_srv_now_ts() - sl_ts) / 60.0
        if left_min > 0:
            return True, (f"cooldown после SL по {symbol}: осталось {left_min:.0f} "
                          f"из {cool:.0f} мин ({int(rec.get('sl_n') or 0)} стоп(ов) за день)")
    return False, ''


def ok(symbol, cfg=None, balance=None):
    """True — вход по символу разрешён. Причина печатается один раз на символ."""
    blocked, why = block_reason(symbol, cfg, balance)
    if not blocked:
        _WARNED.discard(str(symbol))
        return True
    if str(symbol) not in _WARNED:
        _WARNED.add(str(symbol))
        print(f"  -> [GUARD] Пропущен вход {symbol}: {why}", flush=True)
    return False


def snapshot(cfg=None, balance=None):
    """Свежая картина по символам (для дэша/логов): {symbol: {...блоки}}."""
    out = {}
    for symbol, rec in refresh(cfg, force=True).items():
        _blocked, why = block_reason(symbol, cfg, balance)
        out[symbol] = dict(rec)
        out[symbol]['blocked'] = _blocked
        out[symbol]['reason'] = why
    return out


def main():
    """CLI: python symbol_guard.py [--show] — что видит защита по символам."""
    import argparse

    ap = argparse.ArgumentParser(description='Защита по символу: дневной стоп + cooldown')
    ap.add_argument('--show', action='store_true', help='напечатать состояние на сегодня')
    ap.parse_args()

    from config import RiskParams
    cfg = RiskParams()
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            print('  [GUARD] нет соединения с MT5', flush=True)
            return 1
        acc = mt5.account_info()
        bal = float(getattr(acc, 'balance', 0.0) or 0.0) if acc is not None else 0.0
        print(f"  [GUARD] серверных суток: {_srv_now():%Y-%m-%d} | баланс {bal:,.0f} ₽ | "
              f"стоп по символу −{cfg.symbol_day_loss_pct:.1f}% = {bal * cfg.symbol_day_loss_pct / 100.0:,.0f} ₽ | "
              f"cooldown после SL {cfg.symbol_sl_cooldown_min} мин", flush=True)
        snap = snapshot(cfg, bal)
        if not snap:
            print('  [GUARD] сегодня наших сделок ещё нет — блокировок нет', flush=True)
            return 0
        for symbol in sorted(snap, key=lambda k: snap[k]['profit']):
            rec = snap[symbol]
            _mark = 'ЗАБЛОКИРОВАН' if rec['blocked'] else 'ок'
            print(f"  [GUARD] {symbol:<12} реализовано {rec['profit']:+10,.0f} ₽ | "
                  f"сделок {rec['n']:>3} | стопов {rec['sl_n']:>2} | {_mark}"
                  + (f" — {rec['reason']}" if rec['blocked'] else ''), flush=True)
    finally:
        try:
            import MetaTrader5 as mt5
            mt5.shutdown()
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
