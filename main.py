import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd
import os
import time
import csv
from itertools import product
from functions import terminal_on, get_non_usd, calc_metrics, composite_score,deduplicate_results
from strategies.stochastic import calc_stochastic, backtest, check_entry, check_exit


# ═══ КОНФИГУРАЦИЯ ═══
SYMBOLS = ["EURUSDrfd", "GBPUSDrfd", "USDJPYrfd", "USDCHFrfd",
           "USDCADrfd", "AUDUSDrfd", "NZDUSDrfd"]


K_PERIOD_RANGE  = (7, 28, 7)
SL_POINTS_RANGE = (300, 1200, 200)
TP_POINTS_RANGE = (300, 1200, 200)

K_PERIODS      = list(range(*K_PERIOD_RANGE[:2], K_PERIOD_RANGE[2])) + [K_PERIOD_RANGE[1]]
SL_POINTS_LIST = list(range(*SL_POINTS_RANGE[:2], SL_POINTS_RANGE[2])) + [SL_POINTS_RANGE[1]]
TP_POINTS_LIST = list(range(*TP_POINTS_RANGE[:2], TP_POINTS_RANGE[2])) + [TP_POINTS_RANGE[1]]

LOT_PER_STRATEGY = 0.1
BACKTEST_DAYS = 30
TOP_N = 5
RERANK_MINUTES = 10
POLL_INTERVAL = 5
MAGIC_BASE = 770000

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_DIR = os.path.join(BASE_DIR, "journals")
RANKING_FILE = os.path.join(JOURNAL_DIR, "rankings.txt")
JOURNAL_FILE = os.path.join(JOURNAL_DIR, f"journal_{datetime.now().strftime('%Y%m')}.csv")

COLUMNS = ['symbol', 'k_period', 'sl_points', 'tp_points',
           'entry_time', 'exit_time', 'direction',
           'entry_price', 'exit_price', 'lot', 'profit',
           'exit_reason', 'ticket']

# ═══ ПОДКЛЮЧЕНИЕ ═══
connection = terminal_on('demo')
os.makedirs(JOURNAL_DIR, exist_ok=True)



# ═══ КЭШ H1 (общий по символам) ═══
symbol_data = {}


def load_h1(symbol):
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5,
                                 datetime.now() - timedelta(days=90), datetime.now())
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("time")[["open", "high", "low", "close"]]
    df = df.groupby(pd.Grouper(freq="1h")).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return df


print("Загрузка истории...")
for sym in SYMBOLS:
    h1 = load_h1(sym)
    if h1 is not None:
        mt5.symbol_select(sym, True)
        info = mt5.symbol_info(sym)
        symbol_data[sym] = {
            'df_h1': h1,
            'current_hour': (h1.index[-1] + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0),
            'forming_bar': None,
            'info': info,
        }
        print(f"  {sym}: {len(h1)} баров H1")
    else:
        print(f"  {sym}: нет данных")


def update_symbol_bar(symbol, bid, ask, now):
    """Обновляет формирующийся бар. Возвращает True если бар закрылся."""
    sd = symbol_data[symbol]
    bar_hour = now.replace(minute=0, second=0, microsecond=0)
    finalized = False
    if bar_hour != sd['current_hour']:
        if sd['forming_bar'] is not None:
            new_row = pd.DataFrame(
                {'open': sd['forming_bar']['open'], 'high': sd['forming_bar']['high'],
                 'low': sd['forming_bar']['low'], 'close': sd['forming_bar']['close']},
                index=pd.DatetimeIndex([sd['current_hour']])
            )
            sd['df_h1'] = pd.concat([sd['df_h1'], new_row])
            finalized = True
            print(f"\n[{symbol}] Бар {sd['current_hour']} закрыт")
        sd['current_hour'] = bar_hour
        sd['forming_bar'] = {'open': ask, 'high': ask, 'low': bid, 'close': bid}
    else:
        if sd['forming_bar'] is None:
            sd['forming_bar'] = {'open': ask, 'high': ask, 'low': bid, 'close': bid}
        else:
            sd['forming_bar']['high'] = max(sd['forming_bar']['high'], ask)
            sd['forming_bar']['low'] = min(sd['forming_bar']['low'], bid)
            sd['forming_bar']['close'] = bid
    return finalized


# ═══ ЖУРНАЛ ═══
def load_journal():
    if os.path.exists(JOURNAL_FILE):
        return pd.read_csv(JOURNAL_FILE, parse_dates=['entry_time', 'exit_time'])
    return pd.DataFrame(columns=COLUMNS)


def save_journal(df):
    df.to_csv(JOURNAL_FILE, index=False)


journal_df = load_journal()


def record_trade(trade_dict):
    global journal_df
    journal_df = pd.concat([journal_df, pd.DataFrame([trade_dict])], ignore_index=True)
    save_journal(journal_df)


# ═══ ОРДЕРА ═══
def send_order(symbol, direction, lot, sl, tp, magic, comment):
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return None
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
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        request["type_filling"] = mt5.ORDER_FILLING_IOC
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"  → Ордер не прошёл: {result.retcode}, {result.comment}")
            return None
    print(f"  → {direction.upper()} {symbol}: ticket={result.order}, "
          f"price={price:.{symbol_data[symbol]['info'].digits}f}, lot={lot:.2f}, comment={comment}")
    return result.order


def close_order(symbol, ticket, direction, magic):
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
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        request["type_filling"] = mt5.ORDER_FILLING_IOC
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"  → Закрытие не прошло: {result.retcode}, {result.comment}")
            return None
    print(f"  → Закрыт {symbol} ticket={ticket}, price={price:.{symbol_data[symbol]['info'].digits}f}")
    return price


def get_deal_exit_price(ticket):
    deals = mt5.history_deals_get(datetime.now() - timedelta(hours=48), datetime.now())
    if deals:
        for d in sorted(deals, key=lambda x: x.time, reverse=True):
            if d.position_id == ticket and d.entry == mt5.DEAL_ENTRY_OUT:
                return d.price
    return None


# ═══ БЭКТЕСТ И РЭНКИНГ ═══
def run_backtest():
    """Перебирает все комбинации, возвращает топ-N."""
    results = []
    for symbol in SYMBOLS:
        if symbol not in symbol_data:
            continue
        sd = symbol_data[symbol]
        info = sd['info']
        df_window = sd['df_h1'].tail(BACKTEST_DAYS * 24)
        if len(df_window) < 30:
            continue

        for k, sl, tp in product(K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST):
            profit, n_trades = backtest(
                df_window, k, sl, tp,
                info.point, info.trade_tick_value, info.trade_tick_size,
                spread_points=info.spread
            )
            results.append({
                'symbol': symbol,
                'k_period': k,
                'sl_points': sl,
                'tp_points': tp,
                'profit': profit,
                'n_trades': n_trades,
            })

    results.sort(key=lambda x: x['profit'], reverse=True)
    return results[:TOP_N]


def write_ranking(top_strats, all_results):
    csv_file = os.path.join(JOURNAL_DIR, "rankings.csv")
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['rank', 'symbol', 'k_period', 'sl_points', 'tp_points',
                         'profit', 'pf', 'mdd', 'win_rate', 'sharpe', 'recovery', 'score', 'top'])
        for i, r in enumerate(all_results):
            is_active = any(
                s['symbol'] == r['symbol'] and s['k_period'] == r['k_period']
                and s['sl_points'] == r['sl_points'] and s['tp_points'] == r['tp_points']
                for s in top_strats
            )
            pair = r['symbol'].replace('rfd', '')
            writer.writerow([i+1, pair, r['k_period'], r['sl_points'], r['tp_points'],
                             round(r['profit'], 2), round(r['profit_factor'], 2),
                             round(r['max_drawdown'], 2), round(r['win_rate'], 1),
                             round(r['sharpe'], 2), round(r['recovery'], 1),
                             round(r['score'], 3), "TOP" if is_active else ""])
    # --- TXT для быстрого чтения ---
    txt_file = os.path.join(JOURNAL_DIR, "ranking.txt")
    lines = [
        "=" * 110,
        f"  RANKING | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Окно бэктеста: {BACKTEST_DAYS} дней | Всего комбинаций: {len(all_results)}",
        "=" * 110,
        (f"  {'#':<4} {'Symbol':<12} {'K':>4} {'SL':>5} {'TP':>5} "
         f"{'Profit':>10} {'PF':>6} {'MDD':>8} {'WinR':>6} {'Sharpe':>7} {'Recov':>6} "
         f"{'Score':>7} {'Top':>6}"),
        "-" * 110
    ]

    for i, r in enumerate(all_results):
        is_active_txt = "▶ TOP" if any(
            s['symbol'] == r['symbol'] and s['k_period'] == r['k_period']
            and s['sl_points'] == r['sl_points'] and s['tp_points'] == r['tp_points']
            for s in top_strats
        ) else ""
        lines.append(
            f"  {i+1:<4} {r['symbol']:<12} {r['k_period']:>4} {r['sl_points']:>5} {r['tp_points']:>5} "
            f"{r['profit']:>+9.1f} {r['profit_factor']:>5.2f} {r['max_drawdown']:>+7.1f} "
            f"{r['win_rate']:>5.1f}% {r['sharpe']:>6.2f} {r['recovery']:>5.1f} {r['score']:>6.3f} {is_active_txt:>6}"
        )

    lines += [
        "-" * 110,
        f"  Топ-{TOP_N} активны на демо, лот={LOT_PER_STRATEGY} на каждую",
        "=" * 110
    ]

    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))



# ═══ АКТИВНЫЕ СТРАТЕГИИ ═══
active_strategies = {}  # key -> strategy dict


def strategy_key(symbol, k_period):
    return f"{symbol}_K{k_period}"


def sync_active_strategies(top_results, now):
    """Открывает позиции для новых топ-3, закрывает те, что выпали из топа."""
    global active_strategies

    # Текущие ключи топа
    top_keys = set()
    for r in top_results:
        top_keys.add(strategy_key(r['symbol'], r['k_period']))

    # Закрываем те, что выпали из топа
    to_close = []
    for key, s in active_strategies.items():
        if key not in top_keys:
            to_close.append(key)

    for key in to_close:
        s = active_strategies[key]
        if s['position'] is not None:
            exit_price = close_order(s['symbol'], s['position']['ticket'],
                                     s['position']['direction'], s['magic'])
            if exit_price is not None:
                tick_val = symbol_data[s['symbol']]['info'].trade_tick_value
                tick_size = symbol_data[s['symbol']]['info'].trade_tick_size
                diff = (exit_price - s['position']['entry_price']) if s['position']['direction'] == 'long' \
                    else (s['position']['entry_price'] - exit_price)
                profit = (diff / tick_size) * tick_val * s['position']['lot']
                record_trade({
                    'symbol': s['symbol'], 'k_period': s['k_period'],
                    'sl_points': s['sl_points'], 'tp_points': s['tp_points'],
                    'entry_time': s['position']['entry_time'], 'exit_time': now,
                    'direction': s['position']['direction'],
                    'entry_price': s['position']['entry_price'],
                    'exit_price': exit_price, 'lot': s['position']['lot'],
                    'profit': profit, 'exit_reason': 'rerank', 'ticket': s['position']['ticket']
                })
                print(f"  → [{key}] Закрыт (вышел из топа): profit={profit:.2f} ₽")
            s['position'] = None
        del active_strategies[key]

    # Добавляем новые из топа
    for r in top_results:
        key = strategy_key(r['symbol'], r['k_period'])
        if key not in active_strategies:
            active_strategies[key] = {
                'symbol': r['symbol'],
                'k_period': r['k_period'],
                'sl_points': r['sl_points'],
                'tp_points': r['tp_points'],
                'magic': MAGIC_BASE + hash(key) % 100000,
                'position': None,
            }
            print(f"  → [{key}] Добавлен в топ-{TOP_N}")

    # Проверяем реальные позиции (могли закрыться по SL/TP у брокера)
    for key, s in active_strategies.items():
        if s['position'] is not None:
            pos_check = mt5.positions_get(ticket=s['position']['ticket'])
            if not pos_check:
                exit_price = get_deal_exit_price(s['position']['ticket'])
                if exit_price is None:
                    tick = mt5.symbol_info_tick(s['symbol'])
                    exit_price = tick.bid if s['position']['direction'] == 'long' else tick.ask
                tick_val = symbol_data[s['symbol']]['info'].trade_tick_value
                tick_size = symbol_data[s['symbol']]['info'].trade_tick_size
                diff = (exit_price - s['position']['entry_price']) if s['position']['direction'] == 'long' \
                    else (s['position']['entry_price'] - exit_price)
                profit = (diff / tick_size) * tick_val * s['position']['lot']
                record_trade({
                    'symbol': s['symbol'], 'k_period': s['k_period'],
                    'sl_points': s['sl_points'], 'tp_points': s['tp_points'],
                    'entry_time': s['position']['entry_time'], 'exit_time': now,
                    'direction': s['position']['direction'],
                    'entry_price': s['position']['entry_price'],
                    'exit_price': exit_price, 'lot': s['position']['lot'],
                    'profit': profit, 'exit_reason': 'SL/TP', 'ticket': s['position']['ticket']
                })
                print(f"  → [{key}] Закрыт брокером (SL/TP): profit={profit:.2f} ₽")
                s['position'] = None


def check_active_signals(now):
    """Проверяет сигналы для активных стратегий на закрытом баре."""
    for key, s in active_strategies.items():
        if s['symbol'] not in symbol_data:
            continue
        sd = symbol_data[s['symbol']]
        df = sd['df_h1']

        # Считаем стохастик с k_period этой стратегии
        df = calc_stochastic(df, s['k_period'])
        if len(df) < 2:
            continue

        prev_k = df['k'].iloc[-2]
        last_k = df['k'].iloc[-1]
        info = sd['info']
        digits = info.digits

        # Если есть позиция — проверяем выход
        if s['position'] is not None:
            # Сначала проверка через терминал (мог закрыться SL/TP)
            pos_check = mt5.positions_get(ticket=s['position']['ticket'])
            if not pos_check:
                exit_price = get_deal_exit_price(s['position']['ticket'])
                if exit_price is None:
                    tick = mt5.symbol_info_tick(s['symbol'])
                    exit_price = tick.bid if s['position']['direction'] == 'long' else tick.ask
                tick_val = info.trade_tick_value
                tick_size = info.trade_tick_size
                diff = (exit_price - s['position']['entry_price']) if s['position']['direction'] == 'long' \
                    else (s['position']['entry_price'] - exit_price)
                profit = (diff / tick_size) * tick_val * s['position']['lot']
                record_trade({
                    'symbol': s['symbol'], 'k_period': s['k_period'],
                    'sl_points': s['sl_points'], 'tp_points': s['tp_points'],
                    'entry_time': s['position']['entry_time'], 'exit_time': now,
                    'direction': s['position']['direction'],
                    'entry_price': s['position']['entry_price'],
                    'exit_price': exit_price, 'lot': s['position']['lot'],
                    'profit': profit, 'exit_reason': 'SL/TP', 'ticket': s['position']['ticket']
                })
                print(f"  → [{key}] Закрыт брокером (SL/TP): profit={profit:.2f} ₽")
                s['position'] = None
                continue

            # Выход по сигналу
            if check_exit(prev_k, last_k, s['position']['direction']):
                exit_price = close_order(s['symbol'], s['position']['ticket'],
                                         s['position']['direction'], s['magic'])
                if exit_price is not None:
                    tick_val = info.trade_tick_value
                    tick_size = info.trade_tick_size
                    diff = (exit_price - s['position']['entry_price']) if s['position']['direction'] == 'long' \
                        else (s['position']['entry_price'] - exit_price)
                    profit = (diff / tick_size) * tick_val * s['position']['lot']
                    record_trade({
                        'symbol': s['symbol'], 'k_period': s['k_period'],
                        'sl_points': s['sl_points'], 'tp_points': s['tp_points'],
                        'entry_time': s['position']['entry_time'], 'exit_time': now,
                        'direction': s['position']['direction'],
                        'entry_price': s['position']['entry_price'],
                        'exit_price': exit_price, 'lot': s['position']['lot'],
                        'profit': profit, 'exit_reason': 'signal', 'ticket': s['position']['ticket']
                    })
                    print(f"  → [{key}] Закрыт по сигналу: profit={profit:.2f} ₽")
                    s['position'] = None

        # Если нет позиции — проверяем вход
        if s['position'] is None:
            entry_dir = check_entry(prev_k, last_k)
            if entry_dir:
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
                ticket = send_order(s['symbol'], entry_dir, LOT_PER_STRATEGY,
                                    sl, tp, s['magic'], comment)
                if ticket is not None:
                    s['position'] = {
                        'direction': entry_dir,
                        'entry_price': entry,
                        'entry_time': now,
                        'ticket': ticket,
                        'lot': LOT_PER_STRATEGY,
                    }
                    print(f"  → [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}")


# ═══ ПЕРВЫЙ РАСЧЁТ ═══
print("\nБэктест (первый расчёт)...")
all_results = []
for symbol in SYMBOLS:
    if symbol not in symbol_data:
        continue
    sd = symbol_data[symbol]
    info = sd['info']
    df_window = sd['df_h1'].tail(BACKTEST_DAYS * 24)
    if len(df_window) < 30:
        continue

    for k, sl, tp in product(K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST):
        profit, n_trades, trade_profits = backtest(
            df_window, k, sl, tp,
            info.point, info.trade_tick_value, info.trade_tick_size,
            spread_points=info.spread
        )
        metrics = calc_metrics(trade_profits)
        score = composite_score(metrics)
        all_results.append({
            'symbol': symbol, 'k_period': k,
            'sl_points': sl, 'tp_points': tp,
            'profit': profit,
            'n_trades': n_trades,
            'profit_factor': metrics['profit_factor'],
            'max_drawdown': metrics['max_drawdown'],
            'win_rate': metrics['win_rate'],
            'sharpe': metrics['sharpe'],
            'recovery': metrics['recovery'],
            'score': score,
        })


all_results = deduplicate_results(all_results)
all_results.sort(key=lambda x: x['score'], reverse=True)

# Берём лучшую стратегию для каждого символа
seen_symbols = set()
top_results = []
for r in all_results:
    if r['symbol'] not in seen_symbols:
        top_results.append(r)
        seen_symbols.add(r['symbol'])
    if len(top_results) >= TOP_N:
        break

write_ranking(top_results, all_results)
print(f"Всего комбинаций: {len(all_results)}")
print(f"Топ-{TOP_N}:")
for i, r in enumerate(top_results):
    print(f"  {i + 1}. {r['symbol']} K={r['k_period']} SL={r['sl_points']} TP={r['tp_points']} "
          f"profit={r['profit']:+.1f} PF={r['profit_factor']:.2f} WR={r['win_rate']:.0f}% "
          f"score={r['score']:.3f}")

sync_active_strategies(top_results, datetime.now())
print(f"\nЗапуск цикла. Ctrl+C для остановки.\n")

# ═══ ГЛАВНЫЙ ЦИКЛ ═══
last_rerank = datetime.now()
last_mode_check = datetime.now().date()
signal_processed_bars = {}  # symbol -> set of bar hours already processed

try:
    while True:
        now = datetime.now()

        # Смена дня
        if now.date() != last_mode_check:
            last_mode_check = now.date()
            print(f"\n[{now}] Новый день")

        # Реранк каждые RERANK_MINUTES
        if (now - last_rerank).total_seconds() >= RERANK_MINUTES * 60:
            last_rerank = now
            print(f"\n[{now.strftime('%H:%M:%S')}] Реранк...")
            all_results = []
            for symbol in SYMBOLS:
                if symbol not in symbol_data:
                    continue
                sd = symbol_data[symbol]
                info = sd['info']
                df_window = sd['df_h1'].tail(BACKTEST_DAYS * 24)
                if len(df_window) < 30:
                    continue
                for k, sl, tp in product(K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST):
                    profit, n_trades, trade_profits = backtest(
                        df_window, k, sl, tp,
                        info.point, info.trade_tick_value, info.trade_tick_size,
                        spread_points=info.spread
                    )
                    metrics = calc_metrics(trade_profits)
                    score = composite_score(metrics)
                    all_results.append({
                        'symbol': symbol, 'k_period': k,
                        'sl_points': sl, 'tp_points': tp,
                        'profit': profit, 'n_trades': n_trades,
                        'profit_factor': metrics['profit_factor'],
                        'max_drawdown': metrics['max_drawdown'],
                        'win_rate': metrics['win_rate'],
                        'sharpe': metrics['sharpe'],
                        'recovery': metrics['recovery'],
                        'score': score,
                    })
            all_results.sort(key=lambda x: x['score'], reverse=True)
            top_results = all_results[:TOP_N]
            write_ranking(top_results, all_results)
            sync_active_strategies(top_results, now)
            print(f"  Топ-{TOP_N} обновлён, активных: {len(active_strategies)}")

        # Тики — 7 запросов
        ticks = {}
        for sym in SYMBOLS:
            t = mt5.symbol_info_tick(sym)
            if t is not None:
                ticks[sym] = (t.bid, t.ask)
        if not ticks:
            time.sleep(POLL_INTERVAL)
            continue

        # Обновление баров
        any_finalized = False
        for sym in ticks:
            if sym in symbol_data:
                bid, ask = ticks[sym]
                finalized = update_symbol_bar(sym, bid, ask, now)
                if finalized:
                    any_finalized = True
                    # Запоминаем закрытый бар для обработки сигналов
                    bar_hour = symbol_data[sym]['current_hour'] - timedelta(hours=1)
                    if sym not in signal_processed_bars:
                        signal_processed_bars[sym] = set()
                    signal_processed_bars[sym].add(bar_hour)

        # Проверка сигналов только при закрытии бара
        if any_finalized:
            check_active_signals(now)

        # Статус
        active_pos = sum(1 for s in active_strategies.values() if s['position'] is not None)
        bar_time = symbol_data[SYMBOLS[0]]['current_hour'].strftime('%H:%M') if SYMBOLS[0] in symbol_data else '??'
        top_names = [f"{get_non_usd(r['symbol'])}K{r['k_period']}" for r in top_results]
        print(f"\r[{now.strftime('%H:%M:%S')}] бар {bar_time} | "
              f"активных {len(active_strategies)} | позиций {active_pos} | "
              f"топ: {', '.join(top_names)} | ждём...", end='', flush=True)

        time.sleep(POLL_INTERVAL)

except KeyboardInterrupt:
    print("\nОстановка...")
    save_journal(journal_df)
    mt5.shutdown()
    print("Завершено.")
