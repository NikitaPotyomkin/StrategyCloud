import MetaTrader5 as mt5
from datetime import datetime, timedelta
import os
import sys
import time
import socket

from functions import (
    terminal_on, run_full_backtest, write_ranking, sync_active_strategies,
    check_active_signals, send_order, close_order, get_deal_exit_price,
    strategy_key, make_magic, _record_close,
    get_non_usd, calc_metrics, composite_score, deduplicate_results, _short_name,
    distribute_lots, write_active_state,
)
from strategies.stochastic import (
    calc_stochastic, backtest as backtest_stoch,
    check_entry as check_entry_stoch, check_exit as check_exit_stoch,
)
from strategies.parabolic import (
    calc_parabolic, backtest as backtest_parabolic,
    check_entry as check_entry_parabolic, check_exit as check_exit_parabolic,
)
from data_loader import (
    symbol_data, load_h1, update_symbol_bar,
    load_journal, save_journal, record_trade,
)


# ═══ АВТОРАСПОЗНАВАНИЕ МАШИНЫ ═══
TEST_HOSTNAMES = ['LAPTOP-JU0TU1UM']
CURRENT_HOST = socket.gethostname()
TEST_MODE = any(h.lower() in CURRENT_HOST.lower() for h in TEST_HOSTNAMES)

print(f"Хост: {CURRENT_HOST} → режим: {'TEST' if TEST_MODE else 'LIVE'}")


# ═══ КОНФИГУРАЦИЯ ═══
if TEST_MODE:
    # —– Быстрая обкатка на рабочем компе —–
    SYMBOLS = ["EURUSDrfd", "GBPUSDrfd", "USDJPYrfd"]
    K_PERIOD_RANGE  = (7, 28, 14)
    SL_POINTS_RANGE = (300, 1200, 400)
    TP_POINTS_RANGE = (300, 1200, 400)
    PARABOLIC_STEP_RANGE = (0.02, 0.2, 0.09)
    PARABOLIC_MAX_RANGE  = (0.2, 0.4, 0.1)
    BACKTEST_DAYS = 14
    POLL_INTERVAL = 2
else:
    # —– Боевой режим на кладовке —–
    SYMBOLS = ["EURUSDrfd", "GBPUSDrfd", "USDJPYrfd", "USDCHFrfd",
               "USDCADrfd", "AUDUSDrfd", "NZDUSDrfd"]
    K_PERIOD_RANGE  = (7, 28, 7)
    SL_POINTS_RANGE = (300, 1200, 200)
    TP_POINTS_RANGE = (300, 1200, 200)
    PARABOLIC_STEP_RANGE = (0.02, 0.2, 0.02)
    PARABOLIC_MAX_RANGE  = (0.2, 0.4, 0.05)
    BACKTEST_DAYS = 30
    POLL_INTERVAL = 5

MAX_RISK_PCT = 0.05
MIN_LOT = 0.01
MIN_SCORE = 1.0
NIGHT_BACKTEST_HOUR = 3
MAGIC_BASE = 770000

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_DIR = os.path.join(BASE_DIR, "journals")
JOURNAL_FILE = os.path.join(JOURNAL_DIR, f"journal_{datetime.now().strftime('%Y%m')}.csv")

COLUMNS = ['symbol', 'k_period', 'sl_points', 'tp_points',
           'entry_time', 'exit_time', 'direction',
           'entry_price', 'exit_price', 'lot', 'profit',
           'exit_reason', 'ticket']


# ═══ УТИЛИТЫ ═══
def float_range(start, stop, step):
    """range() для float — включает граничное значение."""
    result = []
    v = start
    while v < stop - 1e-9:
        result.append(round(v, 4))
        v += step
    result.append(round(stop, 4))
    return result


def int_range(start, stop, step):
    """range() для int — включает граничное значение."""
    return list(range(start, stop, step)) + [stop]


K_PERIODS       = int_range(*K_PERIOD_RANGE)
SL_POINTS_LIST  = int_range(*SL_POINTS_RANGE)
TP_POINTS_LIST  = int_range(*TP_POINTS_RANGE)
PARABOLIC_STEPS = float_range(*PARABOLIC_STEP_RANGE)
PARABOLIC_MAXS  = float_range(*PARABOLIC_MAX_RANGE)


# ═══ ЗАПРЕТ СДЕЛОК В ТЕСТЕ ═══
if TEST_MODE:
    _real_send_order = send_order
    _real_close_order = close_order

    def send_order(*args, **kwargs):
        sym = args[0] if args else kwargs.get('symbol', '?')
        direction = args[1] if len(args) > 1 else kwargs.get('direction', '?')
        lot = args[2] if len(args) > 2 else kwargs.get('lot', '?')
        print(f"  [TEST] send_order: {sym} {direction} lot={lot} → НЕТ")
        return None

    def close_order(*args, **kwargs):
        ticket = args[0] if args else kwargs.get('ticket', '?')
        print(f"  [TEST] close_order: ticket={ticket} → НЕТ")
        return None


# ═══ ПОДКЛЮЧЕНИЕ ═══
terminal_on('demo')
os.makedirs(JOURNAL_DIR, exist_ok=True)

# ═══ ЗАГРУЗКА ИСТОРИИ ═══
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

# ═══ ЖУРНАЛ ═══
journal_df = load_journal(JOURNAL_FILE, COLUMNS)


# ═══ АКТИВНЫЕ СТРАТЕГИИ ═══
active_strategies = {}


# ═══ ПЕРВЫЙ РАСЧЁТ ═══
print("\nБэктест (первый расчёт)...")

all_top, all_results = run_full_backtest(
    SYMBOLS, symbol_data, K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST,
    PARABOLIC_STEPS, PARABOLIC_MAXS, BACKTEST_DAYS, 9999,
    backtest_stoch, backtest_parabolic, calc_metrics, composite_score, deduplicate_results
)

acc = mt5.account_info()
balance = acc.balance if acc else 1_000_000
print(f"Баланс: {balance:.0f} руб | Квота риска: {balance * MAX_RISK_PCT:.0f} руб | Порог score >= {MIN_SCORE}")

active = distribute_lots(all_results, symbol_data, balance,
                          MAX_RISK_PCT, MIN_LOT, MIN_SCORE)
print(f"Активировано {len(active)} стратегий из {len(all_results)} комбинаций")

for i, r in enumerate(active):
    stype = r.get('type', 'stoch')
    pmax = r.get('parabolic_max')
    pmax_str = f" Max={pmax:.2f}" if pmax is not None else ""
    print(f"  {i + 1}. {r['symbol']} {stype} K={r['k_period']}{pmax_str} "
          f"SL={r['sl_points']} TP={r['tp_points']} "
          f"profit={r['profit']:+.1f} PF={r['profit_factor']:.2f} "
          f"WR={r['win_rate']:.0f}% score={r['score']:.3f} lot={r['lot']}")

write_ranking(active, all_results, JOURNAL_DIR, BACKTEST_DAYS, len(active), None)

sync_active_strategies(active, datetime.now(), symbol_data, active_strategies,
                       close_order, get_deal_exit_price, record_trade,
                       strategy_key, make_magic, MAGIC_BASE, len(active))

write_active_state(active, active_strategies, balance, MAX_RISK_PCT, JOURNAL_DIR)

print(f"\nЗапуск цикла. Ctrl+C для остановки.\n")


# ═══ ГЛАВНЫЙ ЦИКЛ ═══
last_full_backtest_date = datetime.now().date() - timedelta(days=1)
last_mode_check = datetime.now().date()
last_state_write = datetime.now()
signal_processed_bars = {}

try:
    while True:
        now = datetime.now()

        # Смена дня
        if now.date() != last_mode_check:
            last_mode_check = now.date()
            print(f"\n[{now}] Новый день")

        # Ночной перерасчёт
        if now.hour == NIGHT_BACKTEST_HOUR and now.date() != last_full_backtest_date:
            last_full_backtest_date = now.date()
            print(f"\n[{now.strftime('%H:%M:%S')}] Ночной перерасчёт...")

            _, all_results = run_full_backtest(
                SYMBOLS, symbol_data, K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST,
                PARABOLIC_STEPS, PARABOLIC_MAXS, BACKTEST_DAYS, 9999,
                backtest_stoch, backtest_parabolic, calc_metrics, composite_score, deduplicate_results
            )

            acc = mt5.account_info()
            balance = acc.balance if acc else 1_000_000
            active = distribute_lots(all_results, symbol_data, balance,
                                     MAX_RISK_PCT, MIN_LOT, MIN_SCORE)
            print(f"Баланс: {balance:.0f} руб | Квота: {balance * MAX_RISK_PCT:.0f} руб | "
                  f"Активировано {len(active)} из {len(all_results)}")

            write_ranking(active, all_results, JOURNAL_DIR, BACKTEST_DAYS, len(active), None)
            sync_active_strategies(active, now, symbol_data, active_strategies,
                                   close_order, get_deal_exit_price, record_trade,
                                   strategy_key, make_magic, MAGIC_BASE, len(active))
            write_active_state(active, active_strategies, balance, MAX_RISK_PCT, JOURNAL_DIR)
            print(f"  Готово: {len(all_results)} комбинаций, {len(active)} активных")

        # Тики
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
                    bar_hour = symbol_data[sym]['current_hour'] - timedelta(hours=1)
                    if sym not in signal_processed_bars:
                        signal_processed_bars[sym] = set()
                    signal_processed_bars[sym].add(bar_hour)

        # Проверка сигналов
        if any_finalized:
            check_active_signals(
                now, active_strategies, symbol_data,
                calc_stochastic, check_exit_stoch, check_entry_stoch,
                calc_parabolic, check_exit_parabolic, check_entry_parabolic,
                send_order, close_order, get_deal_exit_price,
                _record_close, MIN_LOT, record_trade
            )

        # Обновление active_state.json примерно раз в минуту
        if (now - last_state_write).total_seconds() >= 60:
            write_active_state(active, active_strategies, balance, MAX_RISK_PCT, JOURNAL_DIR)
            last_state_write = now

        # Статус
        active_pos = sum(1 for s in active_strategies.values() if s['position'] is not None)
        bar_time = symbol_data[SYMBOLS[0]]['current_hour'].strftime('%H:%M') if SYMBOLS[0] in symbol_data else '??'
        top_names = [_short_name(r) for r in active[:7]]
        print(f"\r[{now.strftime('%H:%M:%S')}] бар {bar_time} | "
              f"активных {len(active_strategies)} | позиций {active_pos} | "
              f"топ: {', '.join(top_names)} | ждём...", end='', flush=True)

        time.sleep(POLL_INTERVAL)

except KeyboardInterrupt:
    print("\nОстановка...")
    save_journal(journal_df, JOURNAL_FILE)
    mt5.shutdown()
    print("Завершено.")
