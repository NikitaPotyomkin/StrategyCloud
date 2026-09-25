"""Стратегии, сигналы, ранжирование и дэшборд."""
import json
import csv
import os
import math
import datetime
import numpy as np
import MetaTrader5 as mt5

from risk_manager import (
    calc_metrics, composite_score, distribute_lots,
    _normalize_volume, _position_profit, DEFAULT_LOT
)

# Режим счёта, необходимый для нескольких стратегий на одном символе.
HEDGING_MODE = getattr(mt5, 'ACCOUNT_MARGIN_MODE_RETAIL_HEDGING', 2)

# Символы, для которых уже выводилось предупреждение о netting-счёте.
_NETTING_WARNED = set()


def get_non_usd(symbol):
    """Убрать USD из символа: EURUSDrfd -> EUR, USDJPYrfd -> JPY."""
    pair = symbol[:-3]  # убираем rfd
    base, quote = pair[:3], pair[3:]
    return base if base != "USD" else quote


# ═══ УТИЛИТЫ СТРАТЕГИЙ ═══
def strategy_key(symbol, param, stype='stoch', extra=None):
    if stype == 'parabolic' and extra is not None:
        return f"{symbol}_{stype}_S{param}_M{extra}"
    elif stype in ('macd_rsi', 'bollinger', 'ema_cross', 'rsi_div', 'ichimoku'):
        # Для новых стратегий param — это строка вида "mf12_ms26_rsi14"
        return f"{symbol}_{stype}_{param}"
    return f"{symbol}_{stype}_K{param}"


def make_magic(symbol, stype, param, extra=None):
    """Детерминированный magic-номер на основе параметров стратегии."""
    raw = f"{symbol}_{stype}_{param}_{extra}"
    h = 0
    for ch in raw:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return 770000 + (h % 100000)


def _short_name(r):
    pair = get_non_usd(r['symbol'])
    stype = r.get('type', 'stoch')
    k = r['k_period']
    if stype == 'parabolic':
        return f"{pair}/SAR s{k}"
    elif stype == 'macd_rsi':
        return f"{pair}/MACD+RSI {k}"
    elif stype == 'bollinger':
        return f"{pair}/BB {k}"
    elif stype == 'ema_cross':
        return f"{pair}/EMA {k}"
    elif stype == 'rsi_div':
        return f"{pair}/RSI-Div {k}"
    elif stype == 'ichimoku':
        return f"{pair}/Ichimoku {k}"
    elif stype == 'rf':
        return f"{pair}/RF {k}"
    elif stype == 'logreg':
        return f"{pair}/LogReg {k}"
    return f"{pair}/Stoch K{k}"


# ═══ МЕТРИКИ И СКОРИНГ ═══

def deduplicate_results(results, min_trades=10, min_score=1.0):
    # --- Проход 1: точная дедупликация по параметрам ---
    best = {}
    for r in results:
        stype = r.get('type', 'stoch')
        sym = r['symbol']

        if stype == 'parabolic':
            key = (sym, stype, r['k_period'], r.get('parabolic_max', 0.2))
        else:
            key = (sym, stype, r['k_period'])

        if key not in best or r['score'] > best[key]['score']:
            best[key] = r

    unique = list(best.values())

    # --- Фильтры: мало сделок или слабый score — в топку ---
    unique = [r for r in unique
              if r.get('n_trades', 0) >= min_trades
              and r.get('score', 0) >= min_score]
    unique.sort(key=lambda r: r['score'], reverse=True)

    # --- Лимит по символу: 30% от того, что осталось ---
    n_symbols = len(set(r['symbol'] for r in unique))
    max_per_symbol = max(1, math.ceil(len(unique) * 0.3 / max(n_symbols, 1))) #хардкод

    # --- Проход 2: похожие по результатам + лимит по символу ---
    selected = []
    symbol_counts = {}
    for r in unique:
        sym = r['symbol']
        if symbol_counts.get(sym, 0) >= max_per_symbol:
            continue

        is_similar = False
        for s in selected:
            if r['symbol'] != s['symbol']:
                continue
            profit_close = abs(r['profit'] - s['profit']) / max(abs(r['profit']), 1) < 0.05 #хардкод
            n_trades_r = r.get('n_trades', 0)
            n_trades_s = s.get('n_trades', 0)
            trades_close = abs(n_trades_r - n_trades_s) / max(n_trades_r, 1) < 0.10  #хардкод
            if profit_close and trades_close:
                is_similar = True
                break
        if not is_similar:
            selected.append(r)
            symbol_counts[sym] = symbol_counts.get(sym, 0) + 1

    return selected




# ═══ РАНИРОВАНИЕ И ДЭШБОРД ═══
def write_ranking(top_strats, all_results, JOURNAL_DIR, BACKTEST_DAYS, TOP_N, LOT_PER_STRATEGY):
    # --- CSV ---
    csv_file = os.path.join(JOURNAL_DIR, "rankings.csv")
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['rank', 'symbol', 'type', 'k_period', 'parabolic_max',
                         'sl_points', 'tp_points',
                         'profit', 'pf', 'mdd', 'win_rate', 'sharpe',
                         'recovery', 'score', 'top'])
        for i, r in enumerate(all_results):
            is_active = any(
                s['symbol'] == r['symbol'] and s['k_period'] == r['k_period']
                and s['sl_points'] == r['sl_points'] and s['tp_points'] == r['tp_points']
                and s.get('type', 'stoch') == r.get('type', 'stoch')
                and s.get('parabolic_max') == r.get('parabolic_max')
                for s in top_strats
            )
            pair = r['symbol'].replace('rfd', '')
            stype = r.get('type', 'stoch')
            pmax = r.get('parabolic_max')
            pmax_str = f"{pmax:.2f}" if pmax is not None else ""
            writer.writerow([i+1, pair, stype, r['k_period'], pmax_str,
                             r['sl_points'], r['tp_points'],
                             round(r['profit'], 2), round(r['profit_factor'], 2),
                             round(r['max_drawdown'], 2), round(r['win_rate'], 1),
                             round(r['sharpe'], 2), round(r['recovery'], 1),
                             round(r['score'], 3), "TOP" if is_active else ""])

    # --- TXT ---
    txt_file = os.path.join(JOURNAL_DIR, "ranking.txt")
    lot_label = LOT_PER_STRATEGY if LOT_PER_STRATEGY is not None else '-'
    lines = [
        "=" * 120,
        f"  RANKING | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Окно бэктеста: {BACKTEST_DAYS} дней | Всего комбинаций: {len(all_results)}",
        "=" * 120,
        (f"  {'#':<4} {'Symbol':<12} {'Type':<8} {'K/Step':>6} {'Max':>5} {'SL':>5} {'TP':>5} "
         f"{'Profit':>10} {'PF':>6} {'MDD':>8} {'WinR':>6} {'Sharpe':>7} {'Recov':>6} "
         f"{'Score':>7} {'Top':>6}"),
        "-" * 120
    ]

    for i, r in enumerate(all_results):
        is_active_txt = "* TOP" if any(
            s['symbol'] == r['symbol'] and s['k_period'] == r['k_period']
            and s['sl_points'] == r['sl_points'] and s['tp_points'] == r['tp_points']
            and s.get('type', 'stoch') == r.get('type', 'stoch')
            and s.get('parabolic_max') == r.get('parabolic_max')
            for s in top_strats
        ) else ""
        stype = r.get('type', 'stoch')
        k_or_step = r['k_period']
        pmax = r.get('parabolic_max')
        pmax_str = f"{pmax:.2f}" if pmax is not None else ""
        lines.append(
            f"  {i+1:<4} {r['symbol']:<12} {stype:<8} {k_or_step:>6} {pmax_str:>5} "
            f"{r['sl_points']:>5} {r['tp_points']:>5} "
            f"{r['profit']:>+9.1f} {r['profit_factor']:>5.2f} {r['max_drawdown']:>+7.1f} "
            f"{r['win_rate']:>5.1f}% {r['sharpe']:>6.2f} {r['recovery']:>5.1f} "
            f"{r['score']:>6.3f} {is_active_txt:>6}"
        )

    lines += [
        "-" * 120,
        f"  Топ-{TOP_N} активны на демо, лот={lot_label} на каждую",
        "=" * 120
    ]

    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def write_active_state(active, active_strategies, balance, max_risk_pct, journal_dir):
    """Сохраняет текущее состояние активных стратегий для Streamlit-дэшборда."""
    state = {
        'updated': datetime.datetime.now().isoformat(),
        'balance': balance,
        'quota': balance * max_risk_pct,
        'total_strategies': len(active),
        'strategies': []
    }
    for r in active:
        key = strategy_key(r['symbol'], r['k_period'], r.get('type', 'stoch'),
                           r.get('parabolic_max'))
        strat = active_strategies.get(key, {})
        has_position = strat.get('position') is not None
        state['strategies'].append({
            'symbol': r['symbol'],
            'type': r.get('type', 'stoch'),
            'k_period': r.get('k_period', '-'),
            'sl_points': r.get('sl_points', '-'),
            'tp_points': r.get('tp_points', '-'),
            'parabolic_step': r.get('parabolic_step', '-'),
            'parabolic_max': r.get('parabolic_max', '-'),
            'score': r['score'],
            'lot': r['lot'],
            'profit': r.get('profit', 0),
            'profit_factor': r.get('profit_factor', 0),
            'win_rate': r.get('win_rate', 0),
            'n_trades': r.get('n_trades', 0),
            'has_position': has_position,
        })
    path = os.path.join(journal_dir, 'active_state.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ═══ СИНХРОНИЗАЦИЯ АКТИВНЫХ СТРАТЕГИЙ ═══
def sync_active_strategies(top_results, now, symbol_data, active_strategies, close_order_fn,
                           get_deal_exit_price_fn, record_trade_fn, strategy_key_fn,
                           make_magic_fn, MAGIC_BASE, TOP_N):
    """Открывает позиции для новых топ-N, закрывает те, что выпали из топа."""
    # Текущие ключи топа
    top_keys = set()
    for r in top_results:
        stype = r.get('type', 'stoch')
        param = r['k_period']
        extra = r.get('parabolic_max')
        top_keys.add(strategy_key_fn(r['symbol'], param, stype, extra))

    # Закрываем те, что выпали из топа
    to_close = [key for key in active_strategies if key not in top_keys]

    for key in to_close:
        s = active_strategies[key]
        if s['position'] is not None:
            exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                        s['position']['direction'], s['magic'], symbol_data)
            if exit_price is not None:
                _record_close(key, s, now, exit_price, 'rerank', symbol_data, record_trade_fn)
            else:
                # Закрыть не удалось — не теряем позицию из виду.
                # Стратегия остаётся под управлением до успешного закрытия.
                print(f"  -> [{key}] Не удалось закрыть (rerank) — позиция остаётся под управлением")
                continue
        del active_strategies[key]

    # Добавляем новые из топа
    existing_magics = {s['magic'] for s in active_strategies.values()}
    for r in top_results:
        stype = r.get('type', 'stoch')
        param = r['k_period']
        extra = r.get('parabolic_max')
        key = strategy_key_fn(r['symbol'], param, stype, extra)
        if key not in active_strategies:
            magic = make_magic_fn(r['symbol'], stype, param, extra)
            if magic in existing_magics:
                print(f"  -> [WARN] Коллизия magic {magic} у {key} — стратегия пропущена")
                continue
            strat_dict = {
                'symbol': r['symbol'],
                'k_period': param,
                'parabolic_max': r.get('parabolic_max'),
                'sl_points': r['sl_points'],
                'tp_points': r['tp_points'],
                'type': stype,
                'magic': magic,
                'lot': r.get('lot', DEFAULT_LOT),
                'position': None,
            }
            # RF-specific params
            if stype == 'rf':
                k = param  # "lb200_nb5_th0.60"
                for p in k.split('_'):
                    if p.startswith('lb'):
                        strat_dict['lookback'] = int(p[2:])
                    elif p.startswith('nb'):
                        strat_dict['n_bars'] = int(p[2:])
                    elif p.startswith('th'):
                        strat_dict['threshold'] = float(p[2:])
            # LogReg-specific params
            elif stype == 'logreg':
                k = param  # "lb100_nb12_th0.55"
                for p in k.split('_'):
                    if p.startswith('lb'):
                        strat_dict['lookback'] = int(p[2:])
                    elif p.startswith('nb'):
                        strat_dict['n_bars'] = int(p[2:])
                    elif p.startswith('th'):
                        strat_dict['threshold'] = float(p[2:])
            active_strategies[key] = strat_dict
            existing_magics.add(magic)
            print(f"  -> [{key}] Добавлен в топ-{TOP_N}, lot={strat_dict['lot']}")

    # Проверяем реальные позиции (могли закрыться по SL/TP у брокера)
    for key, s in active_strategies.items():
        if s['position'] is not None and not mt5.positions_get(ticket=s['position']['ticket']):
            _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                  _record_close, record_trade_fn)


# ═══ РАБОТА С ОРДЕРАМИ И ПОЗИЦИЯМИ ═══

def get_deal_exit_price(ticket, since=None):
    """Цена закрывающей сделки (DEAL_ENTRY_OUT) по position-тикету.

    since — нижняя граница поиска в истории. По умолчанию 30 суток:
    позиция может жить дольше 48 ч, и по SL/TP она попадёт за пределами
    старого окна (тогда цена искажалась текущим тиком).
    """
    if since is None:
        since = datetime.datetime.now() - datetime.timedelta(days=30)
    deals = mt5.history_deals_get(since, datetime.datetime.now())
    if deals:
        for d in sorted(deals, key=lambda x: x.time, reverse=True):
            if d.position_id == ticket and d.entry == mt5.DEAL_ENTRY_OUT:
                return d.price
    return None


def _record_close(key, s, now, exit_price, reason, symbol_data, record_trade_fn,
                  journal_df=None, JOURNAL_FILE=None):
    """Общая логика записи закрытия сделки в журнал. Возвращает profit."""
    profit = _position_profit(s, exit_price, symbol_data)
    trade = {
        'symbol': s['symbol'], 'k_period': s['k_period'],
        'sl_points': s['sl_points'], 'tp_points': s['tp_points'],
        'entry_time': s['position']['entry_time'], 'exit_time': now,
        'direction': s['position']['direction'],
        'entry_price': s['position']['entry_price'],
        'exit_price': exit_price, 'lot': s['position']['lot'],
        'profit': profit, 'exit_reason': reason, 'ticket': s['position']['ticket']
    }
    # Пытаемся записать в журнал; если journal_df/JOURNAL_FILE не переданы — пропускаем
    if journal_df is not None and JOURNAL_FILE is not None:
        record_trade_fn(trade, journal_df, JOURNAL_FILE)
    print(f"  -> [{key}] Закрыт ({reason}): profit={profit:.2f}")
    s['position'] = None
    return profit


def _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                          _record_close_fn, record_trade_fn):
    """Если позиции уже нет на брокере (SL/TP) — фиксируем закрытие.

    Возвращает True, если позиция закрыта и записана в журнал.
    """
    if mt5.positions_get(ticket=s['position']['ticket']):
        return False
    exit_price = get_deal_exit_price_fn(s['position']['ticket'], since=s['position']['entry_time'])
    if exit_price is None:
        tick = mt5.symbol_info_tick(s['symbol'])
        if tick is None:
            # Ни сделки, ни тика — откладываем до следующего цикла.
            return False
        exit_price = tick.bid if s['position']['direction'] == 'long' else tick.ask
    _record_close_fn(key, s, now, exit_price, 'SL/TP', symbol_data)
    return True


def check_account_mode():
    """True — счёт hedging.

    Архитектура бота (позиция = тикет стратегии) рассчитана на hedging-счёт:
    на netting несколько стратегий одного символа сольются в одну позицию,
    и закрытие по тикету закроет весь объём символа.
    Вызови на старте в main.py и не торгуй на netting без изменений логики.
    """
    acc = mt5.account_info()
    if acc is None:
        return False
    ok = getattr(acc, 'margin_mode', None) == HEDGING_MODE
    if not ok:
        print(f"  [WARN] Счёт {getattr(acc, 'login', '?')} (сервер {getattr(acc, 'server', '?')}) "
              f"НЕ hedging: несколько стратегий на одном символе будут сливаться!")
    return ok


def send_order(symbol, direction, lot, sl, tp, magic, comment, symbol_data):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None

    info = symbol_data.get(symbol, {}).get('info')
    if info is not None:
        lot = _normalize_volume(lot, info)
        if lot is None:
            print(f"  -> {symbol}: объём вне [min, max] или шаг некорректен — отказ")
            return None
    digits = info.digits if info is not None else 5

    # Один раз на символ предупреждаем про netting-счёт
    acc = mt5.account_info()
    if acc is not None and getattr(acc, 'margin_mode', None) != HEDGING_MODE:
        if symbol not in _NETTING_WARNED and mt5.positions_get(symbol=symbol):
            _NETTING_WARNED.add(symbol)
            print(f"  -> [WARN] {symbol}: счёт НЕ hedging — новый объём сольётся с открытой позицией")

    if direction == 'long':
        order_type, price = mt5.ORDER_TYPE_BUY, tick.ask
    else:
        order_type, price = mt5.ORDER_TYPE_SELL, tick.bid
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": lot,
        "type": order_type, "price": price, "sl": sl, "tp": tp,
        "deviation": 20, "comment": comment, "magic": magic,
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_FOK
    }
    result = mt5.order_send(request)
    if result is None:
        print(f"  -> [WARN] mt5.order_send вернул None — терминал не отвечает, ордер пропущен")
        return None
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        # Предупреждение о причинах отказа
        if result.retcode == mt5.TRADE_RETCODE_INVALID_STOPS:
            print(f"  -> [WARN] Ордер {symbol} {direction}: invalid stops (SL/TP) — "
                  f"возможно, SL/TP ближе чем SYMBOL_TRADE_STOPS_LEVEL. "
                  f"SL={sl:.{digits}f} TP={tp:.{digits}f} price={price:.{digits}f}")
        elif result.retcode == mt5.TRADE_RETCODE_INVALID_VOLUME:
            print(f"  -> [WARN] Ордер {symbol} {direction}: invalid volume — "
                  f"lot={lot:.2f} вне [min, max] или шаг")
        request["type_filling"] = mt5.ORDER_FILLING_IOC
        result = mt5.order_send(request)
        if result is None:
            print(f"  -> [WARN] mt5.order_send (IOC) вернул None — терминал не отвечает")
            return None
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"  -> Ордер не прошёл: {result.retcode}, {result.comment}")
            return None
    # Для последующих positions_get/закрытий нужен именно тикет позиции.
    ticket = result.position if result.position else result.order
    print(f"  -> {direction.upper()} {symbol}: ticket={ticket}, "
          f"price={price:.{digits}f}, lot={lot:.2f}, comment={comment}")
    return ticket


def close_order(symbol, ticket, direction, magic, symbol_data):
    pos_info = mt5.positions_get(ticket=ticket)
    if not pos_info:
        return None
    pos = pos_info[0]
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
    if direction == 'long':
        close_type, price = mt5.ORDER_TYPE_SELL, tick.bid
    else:
        close_type, price = mt5.ORDER_TYPE_BUY, tick.ask
    request = {
        "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": pos.volume,
        "position": ticket, "type": close_type, "price": price,
        "deviation": 20, "comment": "close", "magic": magic,
        "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_FOK
    }
    result = mt5.order_send(request)
    if result is None:
        print(f"  -> [WARN] mt5.order_send (close) вернул None — терминал не отвечает")
        return None
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        request["type_filling"] = mt5.ORDER_FILLING_IOC
        result = mt5.order_send(request)
        if result is None:
            print(f"  -> [WARN] mt5.order_send (close IOC) вернул None — терминал не отвечает")
            return None
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"  -> Закрытие не прошло: {result.retcode}, {result.comment}")
            return None
    digits = symbol_data[symbol]['info'].digits
    print(f"  -> Закрыт {symbol} ticket={ticket}, price={price:.{digits}f}")
    return price


# ═══ ПРОВЕРКА СИГНАЛОВ ═══
def check_active_signals(now, active_strategies, symbol_data, calc_stochastic_fn,
                         check_exit_stoch_fn, check_entry_stoch_fn, calc_parabolic_fn,
                         check_exit_parabolic_fn, check_entry_parabolic_fn,
                         calc_moving_average_fn, check_exit_ma_fn, check_entry_ma_fn,
                         send_order_fn, close_order_fn, get_deal_exit_price_fn,
                         _record_close_fn, LOT_PER_STRATEGY, record_trade_fn,
                         journal_df=None, JOURNAL_FILE=None,
                         calc_random_forest_fn=None, check_exit_rf_fn=None,
                         check_entry_rf_fn=None,
                         calc_logreg_fn=None, check_exit_logreg_fn=None,
                         check_entry_logreg_fn=None,
                         calc_macd_rsi_fn=None, check_exit_macd_rsi_fn=None,
                         check_entry_macd_rsi_fn=None,
                         calc_bollinger_fn=None, check_exit_bollinger_fn=None,
                         check_entry_bollinger_fn=None,
                         calc_ema_crossover_fn=None, check_exit_ema_crossover_fn=None,
                         check_entry_ema_crossover_fn=None,
                         calc_rsi_divergence_fn=None, check_exit_rsi_divergence_fn=None,
                         check_entry_rsi_divergence_fn=None,
                         calc_ichimoku_fn=None, check_exit_ichimoku_fn=None,
                         check_entry_ichimoku_fn=None):
    """Проверяет сигналы для активных стратегий на закрытом баре.

    Правило: на одну комбинацию (символ + тип стратегии) — максимум 1 открытая позиция.
    RF и LogReg-аргументы опциональны.
    """
    # Собираем занятые (символ, тип) из открытых позиций
    occupied = set()
    for s in active_strategies.values():
        if s['position'] is not None:
            occupied.add((s['symbol'], s.get('type', 'stoch')))

    for key, s in active_strategies.items():
        try:
            if s['symbol'] not in symbol_data:
                continue
            sd = symbol_data[s['symbol']]
            df = sd['df_h1']

            stype = s.get('type', 'stoch')
            info = sd['info']
            digits = info.digits

            if stype == 'stoch':
                df = calc_stochastic_fn(df, s['k_period'])
                if df is None or len(df) < 2:
                    continue

                prev_k = df['k'].iloc[-2]
                last_k = df['k'].iloc[-1]

                # ── Если есть позиция — проверяем выход ──
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue

                    if check_exit_stoch_fn(prev_k, last_k, s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)

                # ── Если нет позиции — проверяем вход ──
                if s['position'] is None:
                    entry_dir = check_entry_stoch_fn(prev_k, last_k)
                    if entry_dir:
                        if (s['symbol'], stype) in occupied:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/{stype}")
                            continue
                        tick = mt5.symbol_info_tick(s['symbol'])
                        if tick is None:
                            continue
                        sl_dist = s['sl_points'] * info.point
                        tp_dist = s['tp_points'] * info.point
                        if entry_dir == 'long':
                            entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                        else:
                            entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist

                        comment = f"{s['symbol']}, K={s['k_period']}"
                        ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                               sl, tp, s['magic'], comment, symbol_data)
                        if ticket is not None:
                            s['position'] = {
                                'direction': entry_dir,
                                'entry_price': entry,
                                'entry_time': now,
                                'ticket': ticket,
                                'lot': s['lot'],
                            }
                            occupied.add((s['symbol'], stype))
                            print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'parabolic':
                df = calc_parabolic_fn(df, s['k_period'], s.get('parabolic_max', 0.2))
                if df is None or len(df) < 2:
                    continue

                prev_sar = df['sar'].iloc[-2]
                current_sar = df['sar'].iloc[-1]
                prev_close = df['close'].iloc[-2]
                current_close = df['close'].iloc[-1]

                # ── Если есть позиция — проверяем выход ──
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue

                    if check_exit_parabolic_fn(prev_sar, current_sar, prev_close, current_close,
                                               s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)

                # ── Если нет позиции — проверяем вход ──
                if s['position'] is None:
                    entry_dir = check_entry_parabolic_fn(prev_sar, current_sar, prev_close, current_close)
                    if entry_dir:
                        if (s['symbol'], 'parabolic') in occupied:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/parabolic")
                            continue
                        tick = mt5.symbol_info_tick(s['symbol'])
                        if tick is None:
                            continue
                        sl_dist = s['sl_points'] * info.point
                        tp_dist = s['tp_points'] * info.point
                        if entry_dir == 'long':
                            entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                        else:
                            entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist

                        comment = f"{s['symbol']}, Step={s['k_period']}, Max={s.get('parabolic_max', 0.2)}"
                        ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                               sl, tp, s['magic'], comment, symbol_data)
                        if ticket is not None:
                            s['position'] = {
                                'direction': entry_dir,
                                'entry_price': entry,
                                'entry_time': now,
                                'ticket': ticket,
                                'lot': s['lot'],
                            }
                            occupied.add((s['symbol'], 'parabolic'))
                            print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'ma':
                df = calc_moving_average_fn(df, s['k_period'])
                if df is None or len(df) < 2:
                    continue

                prev_ma = df['ma'].iloc[-2]
                curr_ma = df['ma'].iloc[-1]
                prev_close = df['close'].iloc[-2]
                curr_close = df['close'].iloc[-1]

                # ── Если есть позиция — проверяем выход ──
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue

                    if check_exit_ma_fn(prev_ma, prev_close, curr_ma, curr_close,
                                        s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)

                # ── Если нет позиции — проверяем вход ──
                if s['position'] is None:
                    entry_dir = check_entry_ma_fn(prev_ma, prev_close, curr_ma, curr_close)
                    if entry_dir:
                        if (s['symbol'], 'ma') in occupied:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/ma")
                            continue
                        tick = mt5.symbol_info_tick(s['symbol'])
                        if tick is None:
                            continue
                        sl_dist = s['sl_points'] * info.point
                        tp_dist = s['tp_points'] * info.point
                        if entry_dir == 'long':
                            entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                        else:
                            entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist

                        comment = f"{s['symbol']}, MA={s['k_period']}"
                        ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                               sl, tp, s['magic'], comment, symbol_data)
                        if ticket is not None:
                            s['position'] = {
                                'direction': entry_dir,
                                'entry_price': entry,
                                'entry_time': now,
                                'ticket': ticket,
                                'lot': s['lot'],
                            }
                            occupied.add((s['symbol'], 'ma'))
                            print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'rf':
                if calc_random_forest_fn is None:
                    print(f"  -> [{key}] RF-стратегия, но модуль расчёта не передан — пропуск")
                    continue

                df = calc_random_forest_fn(df, s.get('lookback', 200), s.get('n_bars', 5),
                                           s.get('threshold', 0.6))
                if df is None or len(df) < 2:
                    continue

                prev_signal = df['rf_signal'].iloc[-2]
                curr_signal = df['rf_signal'].iloc[-1]

                # ── Если есть позиция — проверяем выход ──
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue

                    if check_exit_rf_fn(prev_signal, curr_signal, s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)

                # ── Если нет позиции — проверяем вход ──
                if s['position'] is None:
                    entry_dir = check_entry_rf_fn(prev_signal, curr_signal)
                    if entry_dir:
                        if (s['symbol'], 'rf') in occupied:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/rf")
                            continue
                        tick = mt5.symbol_info_tick(s['symbol'])
                        if tick is None:
                            continue
                        sl_dist = s['sl_points'] * info.point
                        tp_dist = s['tp_points'] * info.point
                        if entry_dir == 'long':
                            entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                        else:
                            entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist

                        comment = f"{s['symbol']}, RF {s.get('k_period', '')}"
                        ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                               sl, tp, s['magic'], comment, symbol_data)
                        if ticket is not None:
                            s['position'] = {
                                'direction': entry_dir,
                                'entry_price': entry,
                                'entry_time': now,
                                'ticket': ticket,
                                'lot': s['lot'],
                            }
                            occupied.add((s['symbol'], 'rf'))
                            print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'logreg':
                if calc_logreg_fn is None:
                    print(f"  -> [{key}] LogReg-стратегия, но модуль расчёта не передан — пропуск")
                    continue

                df = calc_logreg_fn(df, s.get('lookback', 100), s.get('n_bars', 12),
                                    s.get('threshold', 0.55))
                if df is None or len(df) < 2:
                    continue

                prev_signal = df['lr_signal'].iloc[-2]
                curr_signal = df['lr_signal'].iloc[-1]

                # ── Если есть позиция — проверяем выход ──
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue

                    if check_exit_logreg_fn(prev_signal, curr_signal, s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)

                # ── Если нет позиции — проверяем вход ──
                if s['position'] is None:
                    entry_dir = check_entry_logreg_fn(prev_signal, curr_signal)
                    if entry_dir:
                        if (s['symbol'], 'logreg') in occupied:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/logreg")
                            continue
                        tick = mt5.symbol_info_tick(s['symbol'])
                        if tick is None:
                            continue
                        sl_dist = s['sl_points'] * info.point
                        tp_dist = s['tp_points'] * info.point
                        if entry_dir == 'long':
                            entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                        else:
                            entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist

                        comment = f"{s['symbol']}, LogReg {s.get('k_period', '')}"
                        ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                               sl, tp, s['magic'], comment, symbol_data)
                        if ticket is not None:
                            s['position'] = {
                                'direction': entry_dir,
                                'entry_price': entry,
                                'entry_time': now,
                                'ticket': ticket,
                                'lot': s['lot'],
                            }
                            occupied.add((s['symbol'], 'logreg'))
                            print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'macd_rsi':
                if calc_macd_rsi_fn is None:
                    print(f"  -> [{key}] MACD+RSI — модуль не передан")
                    continue
                df = calc_macd_rsi_fn(df)
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['signal'].iloc[-2]
                curr_signal = df['signal'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_macd_rsi_fn(prev_signal, curr_signal, s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_macd_rsi_fn(prev_signal, curr_signal)
                    if entry_dir:
                        if (s['symbol'], 'macd_rsi') in occupied:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/macd_rsi")
                            continue
                        tick = mt5.symbol_info_tick(s['symbol'])
                        if tick is None:
                            continue
                        sl_dist = s['sl_points'] * info.point
                        tp_dist = s['tp_points'] * info.point
                        if entry_dir == 'long':
                            entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                        else:
                            entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                        comment = f"{s['symbol']}, MACD+RSI"
                        ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                               sl, tp, s['magic'], comment, symbol_data)
                        if ticket is not None:
                            s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                             'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                            occupied.add((s['symbol'], 'macd_rsi'))
                            print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'bollinger':
                if calc_bollinger_fn is None:
                    print(f"  -> [{key}] Bollinger — модуль не передан")
                    continue
                df = calc_bollinger_fn(df)
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['signal'].iloc[-2]
                curr_signal = df['signal'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_bollinger_fn(prev_signal, curr_signal, s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_bollinger_fn(prev_signal, curr_signal)
                    if entry_dir:
                        if (s['symbol'], 'bollinger') in occupied:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/bollinger")
                            continue
                        tick = mt5.symbol_info_tick(s['symbol'])
                        if tick is None:
                            continue
                        sl_dist = s['sl_points'] * info.point
                        tp_dist = s['tp_points'] * info.point
                        if entry_dir == 'long':
                            entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                        else:
                            entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                        comment = f"{s['symbol']}, Bollinger"
                        ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                               sl, tp, s['magic'], comment, symbol_data)
                        if ticket is not None:
                            s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                             'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                            occupied.add((s['symbol'], 'bollinger'))
                            print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'ema_cross':
                if calc_ema_crossover_fn is None:
                    print(f"  -> [{key}] EMA — модуль не передан")
                    continue
                df = calc_ema_crossover_fn(df)
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['signal'].iloc[-2]
                curr_signal = df['signal'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_ema_crossover_fn(prev_signal, curr_signal, s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_ema_crossover_fn(prev_signal, curr_signal)
                    if entry_dir:
                        if (s['symbol'], 'ema_cross') in occupied:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/ema_cross")
                            continue
                        tick = mt5.symbol_info_tick(s['symbol'])
                        if tick is None:
                            continue
                        sl_dist = s['sl_points'] * info.point
                        tp_dist = s['tp_points'] * info.point
                        if entry_dir == 'long':
                            entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                        else:
                            entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                        comment = f"{s['symbol']}, EMA"
                        ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                               sl, tp, s['magic'], comment, symbol_data)
                        if ticket is not None:
                            s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                             'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                            occupied.add((s['symbol'], 'ema_cross'))
                            print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'rsi_div':
                if calc_rsi_divergence_fn is None:
                    print(f"  -> [{key}] RSI-Div — модуль не передан")
                    continue
                df = calc_rsi_divergence_fn(df)
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['signal'].iloc[-2]
                curr_signal = df['signal'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_rsi_divergence_fn(prev_signal, curr_signal, s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_rsi_divergence_fn(prev_signal, curr_signal)
                    if entry_dir:
                        if (s['symbol'], 'rsi_div') in occupied:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/rsi_div")
                            continue
                        tick = mt5.symbol_info_tick(s['symbol'])
                        if tick is None:
                            continue
                        sl_dist = s['sl_points'] * info.point
                        tp_dist = s['tp_points'] * info.point
                        if entry_dir == 'long':
                            entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                        else:
                            entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                        comment = f"{s['symbol']}, RSI-Div"
                        ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                               sl, tp, s['magic'], comment, symbol_data)
                        if ticket is not None:
                            s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                             'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                            occupied.add((s['symbol'], 'rsi_div'))
                            print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'ichimoku':
                if calc_ichimoku_fn is None:
                    print(f"  -> [{key}] Ichimoku — модуль не передан")
                    continue
                df = calc_ichimoku_fn(df)
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['signal'].iloc[-2]
                curr_signal = df['signal'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_ichimoku_fn(prev_signal, curr_signal, s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_ichimoku_fn(prev_signal, curr_signal)
                    if entry_dir:
                        if (s['symbol'], 'ichimoku') in occupied:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/ichimoku")
                            continue
                        tick = mt5.symbol_info_tick(s['symbol'])
                        if tick is None:
                            continue
                        sl_dist = s['sl_points'] * info.point
                        tp_dist = s['tp_points'] * info.point
                        if entry_dir == 'long':
                            entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                        else:
                            entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                        comment = f"{s['symbol']}, Ichimoku"
                        ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                               sl, tp, s['magic'], comment, symbol_data)
                        if ticket is not None:
                            s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                             'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                            occupied.add((s['symbol'], 'ichimoku'))
                            print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

        except Exception as e:
            print(f"\n[WARN] Ошибка стратегии {key}: {e!r}", flush=True)
            continue
