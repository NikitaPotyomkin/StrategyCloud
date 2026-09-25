import MetaTrader5 as mt5
from datetime import datetime, timedelta
import os
import time
import socket
import warnings
warnings.filterwarnings('ignore')

from functions import terminal_on, run_full_backtest
from risk_manager import calc_metrics, composite_score, distribute_lots
from strategy_engine import (
    write_ranking, sync_active_strategies, check_active_signals,
    send_order, close_order, get_deal_exit_price,
    strategy_key, make_magic, _record_close,
    deduplicate_results, _short_name,
    write_active_state, get_non_usd
)
from strategies.stochastic import (
    calc_stochastic, backtest as backtest_stoch,
    check_entry as check_entry_stoch, check_exit as check_exit_stoch,
)
from strategies.parabolic import (
    calc_parabolic, backtest as backtest_parabolic,
    check_entry as check_entry_parabolic, check_exit as check_exit_parabolic,
)
from strategies.moving_average import (
    calc_moving_average, backtest as backtest_ma,
    check_entry as check_entry_ma, check_exit as check_exit_ma,
)
from strategies.macd_rsi import (
    calc_macd_rsi, backtest_macd_rsi,
    check_entry as check_entry_macd_rsi, check_exit as check_exit_macd_rsi,
)
from strategies.bollinger_breakout import (
    calc_bollinger, backtest_bollinger,
    check_entry as check_entry_bollinger, check_exit as check_exit_bollinger,
)
from strategies.ema_crossover import (
    calc_ema_crossover, backtest_ema_crossover,
    check_entry as check_entry_ema_crossover, check_exit as check_exit_ema_crossover,
)
from strategies.rsi_divergence import (
    calc_rsi_divergence, backtest_rsi_divergence,
    check_entry as check_entry_rsi_divergence, check_exit as check_exit_rsi_divergence,
)
from strategies.ichimoku_cloud import (
    calc_ichimoku, backtest_ichimoku,
    check_entry as check_entry_ichimoku, check_exit as check_exit_ichimoku,
)
from strategies.random_forest import (
    calc_random_forest, backtest as backtest_rf,
    check_entry as check_entry_rf, check_exit as check_exit_rf,
)
from strategies.logreg import (
    calc_logreg, backtest as backtest_logreg,
    check_entry as check_entry_logreg, check_exit as check_exit_logreg,
)
from data_loader import (
    symbol_data, load_h1, update_symbol_bar,
    load_journal, save_journal, record_trade,
)


# ═══ АВТОРАСПОЗНАВАНИЕ МАШИНЫ ═══
tumbler = 0

if tumbler == 0:
    TEST_HOSTNAMES = ['LAPTOP-JU0TU1UM']
else:
    TEST_HOSTNAMES = ['FAKE_LAPTOP']

CURRENT_HOST = socket.gethostname()
TEST_MODE = any(h.lower() in CURRENT_HOST.lower() for h in TEST_HOSTNAMES)


# ═══ КОНФИГУРАЦИЯ ═══
if TEST_MODE:
    # –– Быстрая обкатка на рабочем компе ––
    # ── Тестируем все стратегии с минимальным перебором параметров ──
    TEST_STRATEGY = None  # все стратегии

    SYMBOLS = ["EURUSDrfd"]
    K_PERIOD_RANGE  = (7, 28, 21)          # [7, 28]
    SL_POINTS_RANGE = (300, 700, 400)      # [300, 700]
    TP_POINTS_RANGE = (300, 700, 400)      # [300, 700]
    PARABOLIC_STEP_RANGE = (0.02, 0.09, 0.07)  # [0.02, 0.09]
    PARABOLIC_MAX_RANGE  = (0.2, 0.3, 0.1)     # [0.2, 0.3]
    MA_PERIOD_RANGE      = (20, 50, 30)      # [20, 50]
    RF_LOOKBACK_RANGE    = (100, 150, 50)    # [100, 150]
    RF_NBARS_RANGE       = (3, 6, 3)         # [3, 6]
    RF_THRESHOLD_RANGE   = (0.55, 0.65, 0.10)  # [0.55, 0.65]
    LOGREG_LOOKBACK_RANGE = (100, 150, 50)   # [100, 150]
    LOGREG_NBARS_RANGE    = (12, 18, 6)      # [12, 18]
    LOGREG_THRESHOLD_RANGE = (0.55, 0.60, 0.05)  # [0.55, 0.60]
    BACKTEST_DAYS = 14
    POLL_INTERVAL = 2
else:
    # –– Боевой режим на кладовке ––
    TEST_STRATEGY = None  # None = все стратегии

    SYMBOLS = ["EURUSDrfd", "GBPUSDrfd", "USDJPYrfd", "USDCHFrfd",
               "USDCADrfd", "AUDUSDrfd", "NZDUSDrfd"]
    K_PERIOD_RANGE  = (7, 28, 7)
    SL_POINTS_RANGE = (300, 1200, 200)
    TP_POINTS_RANGE = (300, 1200, 200)
    PARABOLIC_STEP_RANGE = (0.02, 0.2, 0.02)
    PARABOLIC_MAX_RANGE  = (0.2, 0.4, 0.05)
    MA_PERIOD_RANGE      = (10, 200, 25)

    RF_LOOKBACK_RANGE = (200, 400, 100)  # было (200, 500, 100)
    RF_NBARS_RANGE = (5, 10, 5)  # было (5, 10, 5) — ок
    RF_THRESHOLD_RANGE = (0.55, 0.65, 0.05)  # было (0.60, 0.70, 0.05)

    LOGREG_LOOKBACK_RANGE = (200, 400, 100)
    LOGREG_NBARS_RANGE = (6, 12, 6)
    LOGREG_THRESHOLD_RANGE = (0.55, 0.65, 0.05)

    # MACD + RSI
    MACD_FAST_RANGE = (10, 14, 2)      # [10, 14]
    MACD_SLOW_RANGE = (24, 28, 2)      # [24, 28]
    MACD_SIGNAL_RANGE = (7, 11, 2)     # [7, 11]
    RSI_PERIOD_RANGE = (12, 16, 2)     # [12, 16]
    RSI_OVERSOLD_RANGE = (25, 35, 5)   # [25, 35]
    RSI_OVERBOUGHT_RANGE = (65, 75, 5) # [65, 75]

    # Bollinger
    BB_PERIOD_RANGE = (15, 25, 5)      # [15, 25]
    BB_STD_RANGE = (1.5, 2.5, 0.5)     # [1.5, 2.5]
    VOLUME_PERIOD_RANGE = (15, 25, 5)  # [15, 25]

    # EMA Crossover
    EMA_FAST_RANGE = (8, 12, 1)        # [8, 12]
    EMA_SLOW_RANGE = (18, 24, 2)       # [18, 24]

    # RSI Divergence
    RSI_DIV_PERIOD_RANGE = (12, 16, 2)     # [12, 16]
    RSI_DIV_LOOKBACK_RANGE = (4, 7, 1)     # [4, 7]
    RSI_DIV_THRESHOLD_RANGE = (0.4, 0.6, 0.1)  # [0.4, 0.6]

    # Ichimoku
    TENKAN_RANGE = (7, 12, 2)          # [7, 12]
    KIJUN_RANGE = (22, 30, 4)          # [22, 30]
    SENKOU_B_RANGE = (45, 55, 5)       # [45, 55]
    DISPLACEMENT_RANGE = (22, 30, 4)   # [22, 30]

    BACKTEST_DAYS = 30
    POLL_INTERVAL = 5

MAX_RISK_PCT = 0.05
MIN_LOT = 0.01
MIN_SCORE = 1.0
NIGHT_BACKTEST_HOUR = 3
MAGIC_BASE = 770000

# Допустимое «молчание» терминала до предупреждения о потере связи
CONNECTION_TIMEOUT_SEC = 300      # тиков нет 5 минут — подозрительно (кроме выходных)
CONNECTION_WARN_EVERY_SEC = 600   # повторное предупреждение не чаще раза в 10 минут
JOURNAL_SAVE_EVERY_SEC = 300      # периодическое сохранение журнала (страховка от падения)

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
MA_PERIODS      = int_range(*MA_PERIOD_RANGE)
RF_LOOKBACKS    = int_range(*RF_LOOKBACK_RANGE)
RF_NBARS        = int_range(*RF_NBARS_RANGE)
RF_THRESHOLDS   = float_range(*RF_THRESHOLD_RANGE)
LOGREG_LOOKBACKS    = int_range(*LOGREG_LOOKBACK_RANGE)
LOGREG_NBARS        = int_range(*LOGREG_NBARS_RANGE)
LOGREG_THRESHOLDS   = float_range(*LOGREG_THRESHOLD_RANGE)

# Новые стратегии
MACD_FAST_LIST      = int_range(*MACD_FAST_RANGE)
MACD_SLOW_LIST      = int_range(*MACD_SLOW_RANGE)
MACD_SIGNAL_LIST    = int_range(*MACD_SIGNAL_RANGE)
RSI_PERIOD_LIST     = int_range(*RSI_PERIOD_RANGE)
RSI_OVERSOLD_LIST   = int_range(*RSI_OVERSOLD_RANGE)
RSI_OVERBOUGHT_LIST = int_range(*RSI_OVERBOUGHT_RANGE)

BB_PERIOD_LIST      = int_range(*BB_PERIOD_RANGE)
BB_STD_LIST         = float_range(*BB_STD_RANGE)
VOLUME_PERIOD_LIST  = int_range(*VOLUME_PERIOD_RANGE)

EMA_FAST_LIST       = int_range(*EMA_FAST_RANGE)
EMA_SLOW_LIST       = int_range(*EMA_SLOW_RANGE)

RSI_DIV_PERIOD_LIST     = int_range(*RSI_DIV_PERIOD_RANGE)
RSI_DIV_LOOKBACK_LIST   = int_range(*RSI_DIV_LOOKBACK_RANGE)
RSI_DIV_THRESHOLD_LIST  = float_range(*RSI_DIV_THRESHOLD_RANGE)

TENKAN_LIST       = int_range(*TENKAN_RANGE)
KIJUN_LIST        = int_range(*KIJUN_RANGE)
SENKOU_B_LIST     = int_range(*SENKOU_B_RANGE)
DISPLACEMENT_LIST = int_range(*DISPLACEMENT_RANGE)


# ── Фильтр стратегий для тестового режима ──
def filter_params_for_test():
    """Возвращает только параметры выбранной стратегии, если TEST_STRATEGY задан."""
    if TEST_STRATEGY is None:
        return {}

    param_map = {
        'stoch':  {'K_PERIODS': K_PERIODS, 'SL_POINTS_LIST': SL_POINTS_LIST, 'TP_POINTS_LIST': TP_POINTS_LIST},
        'parabolic': {'PARABOLIC_STEPS': PARABOLIC_STEPS, 'PARABOLIC_MAXS': PARABOLIC_MAXS,
                      'SL_POINTS_LIST': SL_POINTS_LIST, 'TP_POINTS_LIST': TP_POINTS_LIST},
        'ma':     {'MA_PERIODS': MA_PERIODS, 'SL_POINTS_LIST': SL_POINTS_LIST, 'TP_POINTS_LIST': TP_POINTS_LIST},
        'rf':     {'RF_LOOKBACKS': RF_LOOKBACKS, 'RF_NBARS': RF_NBARS, 'RF_THRESHOLDS': RF_THRESHOLDS,
                   'SL_POINTS_LIST': SL_POINTS_LIST, 'TP_POINTS_LIST': TP_POINTS_LIST},
        'logreg': {'LOGREG_LOOKBACKS': LOGREG_LOOKBACKS, 'LOGREG_NBARS': LOGREG_NBARS,
                   'LOGREG_THRESHOLDS': LOGREG_THRESHOLDS,
                   'SL_POINTS_LIST': SL_POINTS_LIST, 'TP_POINTS_LIST': TP_POINTS_LIST},
        'macd_rsi': {'MACD_FAST_LIST': MACD_FAST_LIST, 'MACD_SLOW_LIST': MACD_SLOW_LIST,
                     'MACD_SIGNAL_LIST': MACD_SIGNAL_LIST, 'RSI_PERIOD_LIST': RSI_PERIOD_LIST,
                     'RSI_OVERSOLD_LIST': RSI_OVERSOLD_LIST, 'RSI_OVERBOUGHT_LIST': RSI_OVERBOUGHT_LIST,
                     'SL_POINTS_LIST': SL_POINTS_LIST, 'TP_POINTS_LIST': TP_POINTS_LIST},
        'bollinger': {'BB_PERIOD_LIST': BB_PERIOD_LIST, 'BB_STD_LIST': BB_STD_LIST,
                      'VOLUME_PERIOD_LIST': VOLUME_PERIOD_LIST,
                      'SL_POINTS_LIST': SL_POINTS_LIST, 'TP_POINTS_LIST': TP_POINTS_LIST},
        'ema_cross': {'EMA_FAST_LIST': EMA_FAST_LIST, 'EMA_SLOW_LIST': EMA_SLOW_LIST,
                      'SL_POINTS_LIST': SL_POINTS_LIST, 'TP_POINTS_LIST': TP_POINTS_LIST},
        'rsi_div': {'RSI_DIV_PERIOD_LIST': RSI_DIV_PERIOD_LIST,
                    'RSI_DIV_LOOKBACK_LIST': RSI_DIV_LOOKBACK_LIST,
                    'RSI_DIV_THRESHOLD_LIST': RSI_DIV_THRESHOLD_LIST,
                    'SL_POINTS_LIST': SL_POINTS_LIST, 'TP_POINTS_LIST': TP_POINTS_LIST},
        'ichimoku': {'TENKAN_LIST': TENKAN_LIST, 'KIJUN_LIST': KIJUN_LIST,
                     'SENKOU_B_LIST': SENKOU_B_LIST, 'DISPLACEMENT_LIST': DISPLACEMENT_LIST,
                     'SL_POINTS_LIST': SL_POINTS_LIST, 'TP_POINTS_LIST': TP_POINTS_LIST},
    }
    return param_map.get(TEST_STRATEGY, {})

TEST_PARAMS = filter_params_for_test()


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


if __name__ == '__main__':
    print(f"Хост: {CURRENT_HOST} → режим: {'TEST' if TEST_MODE else 'LIVE'}")
    if TEST_MODE:
        print(f"  ⚡ Тестовый режим: все стратегии, минимальный перебор")
    else:
        print(f"  Боевой режим: все стратегии, полный перебор")

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

    # force_recalc=True — игнорирует чекпоинты и пересчитывает всё с нуля
    FORCE_RECALC = False

    all_top, all_results = run_full_backtest(
        SYMBOLS, symbol_data, K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST,
        PARABOLIC_STEPS, PARABOLIC_MAXS, MA_PERIODS, RF_LOOKBACKS, RF_NBARS, RF_THRESHOLDS,
        LOGREG_LOOKBACKS, LOGREG_NBARS, LOGREG_THRESHOLDS,
        MACD_FAST_LIST, MACD_SLOW_LIST, MACD_SIGNAL_LIST, RSI_PERIOD_LIST,
        RSI_OVERSOLD_LIST, RSI_OVERBOUGHT_LIST,
        BB_PERIOD_LIST, BB_STD_LIST, VOLUME_PERIOD_LIST,
        EMA_FAST_LIST, EMA_SLOW_LIST,
        RSI_DIV_PERIOD_LIST, RSI_DIV_LOOKBACK_LIST, RSI_DIV_THRESHOLD_LIST,
        TENKAN_LIST, KIJUN_LIST, SENKOU_B_LIST, DISPLACEMENT_LIST,
        BACKTEST_DAYS, 9999,
        test_strategy=TEST_STRATEGY,
        test_mode=TEST_MODE,
        force_recalc=FORCE_RECALC
    )

    acc = mt5.account_info()
    balance = acc.balance if acc else 1_000_000
    if acc is not None:
        mode_name = {0: 'demo', 1: 'contest', 2: 'real'}.get(acc.trade_mode, str(acc.trade_mode))
        print(f"Счёт: {acc.login} | Сервер: {acc.server} | Валюта: {acc.currency} | Режим: {mode_name}")
    print(f"Баланс: {balance:.0f} руб | Квота риска: {balance * MAX_RISK_PCT:.0f} руб | Порог score >= {MIN_SCORE}")


    # deduplicate_results уже вызвана внутри run_full_backtest
    deduped_results = all_results
    print(f"После дедупликации: {len(deduped_results)} комбинаций")

    active = distribute_lots(deduped_results, symbol_data, balance,
                             MAX_RISK_PCT, MIN_LOT, MIN_SCORE)


    print(f"Активировано {len(active)} стратегий из {len(deduped_results)} комбинаций")

    for i, r in enumerate(active):
        stype = r.get('type', 'stoch')
        pmax = r.get('parabolic_max')
        pmax_str = f" Max={pmax:.2f}" if pmax is not None else ""
        print(f"  {i + 1}. {r['symbol']} {stype} K={r['k_period']}{pmax_str} "
              f"SL={r['sl_points']} TP={r['tp_points']} "
              f"profit={r['profit']:+.1f} PF={r['profit_factor']:.2f} "
              f"WR={r['win_rate']:.0f}% trades={r['n_trades']} "
              f"score={r['score']:.3f} lot={r['lot']}")

    write_ranking(active, all_results, JOURNAL_DIR, BACKTEST_DAYS, len(active), None)

    sync_active_strategies(active, datetime.now(), symbol_data, active_strategies,
                           close_order, get_deal_exit_price, record_trade,
                           strategy_key, make_magic, MAGIC_BASE, len(active))

    write_active_state(active, active_strategies, balance, MAX_RISK_PCT, JOURNAL_DIR)

    print(f"\nЗапуск цикла. Ctrl+C для остановки.\n")


    # ═══ ГЛАВНЫЙ ЦИКЛ ═══
    # Стартовый бэктест выше считается «сегодняшним» — ночной перерасчёт начнётся с 3:00.
    last_full_backtest_date = datetime.now().date()
    last_mode_check = datetime.now().date()
    last_state_write = datetime.now()
    last_journal_write = datetime.now()
    journal_month = datetime.now().strftime('%Y%m')
    last_ticks_time = datetime.now()
    last_conn_warn_time = datetime.min
    last_balance_refresh = datetime.now()

    try:
        while True:
            now = datetime.now()

            # Смена дня
            if now.date() != last_mode_check:
                last_mode_check = now.date()
                print(f"\n[{now}] Новый день")

            # Ночной перерасчёт: один раз в сутки, начиная с 3:00.
            # Если машина спала в 3:00 — пересчёт выполнится при первом проходе после 3:00.
            if now.hour >= NIGHT_BACKTEST_HOUR and now.date() != last_full_backtest_date:
                last_full_backtest_date = now.date()
                print(f"\n[{now.strftime('%H:%M:%S')}] Ночной перерасчёт...")

                _, all_results = run_full_backtest(
                    SYMBOLS, symbol_data, K_PERIODS, SL_POINTS_LIST, TP_POINTS_LIST,
                    PARABOLIC_STEPS, PARABOLIC_MAXS, MA_PERIODS, RF_LOOKBACKS, RF_NBARS, RF_THRESHOLDS,
                    LOGREG_LOOKBACKS, LOGREG_NBARS, LOGREG_THRESHOLDS,
                    MACD_FAST_LIST, MACD_SLOW_LIST, MACD_SIGNAL_LIST, RSI_PERIOD_LIST,
                    RSI_OVERSOLD_LIST, RSI_OVERBOUGHT_LIST,
                    BB_PERIOD_LIST, BB_STD_LIST, VOLUME_PERIOD_LIST,
                    EMA_FAST_LIST, EMA_SLOW_LIST,
                    RSI_DIV_PERIOD_LIST, RSI_DIV_LOOKBACK_LIST, RSI_DIV_THRESHOLD_LIST,
                    TENKAN_LIST, KIJUN_LIST, SENKOU_B_LIST, DISPLACEMENT_LIST,
                    BACKTEST_DAYS, 9999,
                    test_strategy=TEST_STRATEGY,
                    test_mode=TEST_MODE,
                    force_recalc=FORCE_RECALC
                )

                # Обновляем баланс перед ночным перерасчётом
                acc = mt5.account_info()
                balance = acc.balance if acc else 1_000_000
                # deduplicate_results уже вызвана внутри run_full_backtest
                deduped_results = all_results
                active = distribute_lots(deduped_results, symbol_data, balance,
                                         MAX_RISK_PCT, MIN_LOT, MIN_SCORE)
                print(f"Баланс: {balance:.0f} руб | Квота: {balance * MAX_RISK_PCT:.0f} руб | "
                      f"Активировано {len(active)} из {len(deduped_results)} (всего {len(all_results)})")

                write_ranking(active, all_results, JOURNAL_DIR, BACKTEST_DAYS, len(active), None)
                sync_active_strategies(active, now, symbol_data, active_strategies,
                                       close_order, get_deal_exit_price, record_trade,
                                       strategy_key, make_magic, MAGIC_BASE, len(active))
                write_active_state(active, active_strategies, balance, MAX_RISK_PCT, JOURNAL_DIR)
                print(f"  Готово: {len(all_results)} комбинаций, {len(active)} активных")

            # Периодическое обновление баланса (раз в минуту)
            if (now - last_balance_refresh).total_seconds() >= 60:
                acc = mt5.account_info()
                if acc is not None:
                    balance = acc.balance
                last_balance_refresh = now

            # Тики
            ticks = {}
            for sym in SYMBOLS:
                try:
                    t = mt5.symbol_info_tick(sym)
                    if t is not None:
                        ticks[sym] = (t.bid, t.ask)
                except Exception as e:
                    print(f"\n[WARN] Ошибка получения тика {sym}: {e!r}", flush=True)

            if not ticks:
                idle_sec = (now - last_ticks_time).total_seconds()
                if (idle_sec >= CONNECTION_TIMEOUT_SEC
                        and (now - last_conn_warn_time).total_seconds() >= CONNECTION_WARN_EVERY_SEC):
                    print(f"\n[{now}] ВНИМАНИЕ: тиков нет уже {int(idle_sec // 60)} мин — "
                          f"проверь терминал (отключение/рынок закрыт).", flush=True)
                    last_conn_warn_time = now
                time.sleep(POLL_INTERVAL)
                continue
            last_ticks_time = now

            # Обновление баров
            any_finalized = False
            for sym in ticks:
                if sym in symbol_data:
                    bid, ask = ticks[sym]
                    try:
                        if update_symbol_bar(sym, bid, ask, now):
                            any_finalized = True
                    except Exception as e:
                        print(f"\n[WARN] Ошибка обновления бара {sym}: {e!r}", flush=True)

            # Проверка сигналов
            if any_finalized:
                try:
                    check_active_signals(
                        now, active_strategies, symbol_data,
                        calc_stochastic, check_exit_stoch, check_entry_stoch,
                        calc_parabolic, check_exit_parabolic, check_entry_parabolic,
                        calc_moving_average, check_exit_ma, check_entry_ma,
                        send_order, close_order, get_deal_exit_price,
                        _record_close, MIN_LOT, record_trade,
                        journal_df, JOURNAL_FILE,
                        calc_random_forest, check_exit_rf, check_entry_rf,
                        calc_logreg, check_exit_logreg, check_entry_logreg,
                        calc_macd_rsi, check_exit_macd_rsi, check_entry_macd_rsi,
                        calc_bollinger, check_exit_bollinger, check_entry_bollinger,
                        calc_ema_crossover, check_exit_ema_crossover, check_entry_ema_crossover,
                        calc_rsi_divergence, check_exit_rsi_divergence, check_entry_rsi_divergence,
                        calc_ichimoku, check_exit_ichimoku, check_entry_ichimoku,
                    )
                except Exception as e:
                    print(f"\n[WARN] Ошибка проверки сигналов: {e!r}", flush=True)

            # Обновление active_state.json примерно раз в минуту
            if (now - last_state_write).total_seconds() >= 60:
                write_active_state(active, active_strategies, balance, MAX_RISK_PCT, JOURNAL_DIR)
                last_state_write = now

            # Смена месяца → новый файл журнала
            if now.strftime('%Y%m') != journal_month:
                save_journal(journal_df, JOURNAL_FILE)
                journal_month = now.strftime('%Y%m')
                JOURNAL_FILE = os.path.join(JOURNAL_DIR, f"journal_{journal_month}.csv")
                journal_df = load_journal(JOURNAL_FILE, COLUMNS)
                print(f"\n[{now}] Новый журнал: {JOURNAL_FILE}", flush=True)

            # Периодическое сохранение журнала — страховка на случай падения процесса
            if (now - last_journal_write).total_seconds() >= JOURNAL_SAVE_EVERY_SEC:
                save_journal(journal_df, JOURNAL_FILE)
                last_journal_write = now

            # Статус — компактная агрегированная статистика
            active_pos = sum(1 for s in active_strategies.values() if s['position'] is not None)
            bar_time = '??'
            if SYMBOLS and SYMBOLS[0] in symbol_data:
                bar_time = symbol_data[SYMBOLS[0]]['current_hour'].strftime('%H:%M')
            
            # Агрегация: символ -> тип -> количество стратегий
            from collections import defaultdict
            stats = defaultdict(lambda: defaultdict(int))
            for key, s in active_strategies.items():
                sym = s['symbol']
                stype = s.get('type', 'stoch')
                stats[sym][stype] += 1
            
            # Формирование компактной строки
            sym_stats = []
            for sym in SYMBOLS:
                if sym in stats:
                    type_counts = [f"{t[0].upper()}({c})" for t, c in sorted(stats[sym].items())]
                    sym_stats.append(f"{get_non_usd(sym)}:{','.join(type_counts)}")
            
            status_str = ' | '.join(sym_stats) if sym_stats else 'нет активных'
            print(f"\r[{now.strftime('%H:%M:%S')}] бар {bar_time} | "
                  f"активных {len(active_strategies)} | позиций {active_pos} | "
                  f"{status_str} | ждём...", end='', flush=True)

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nОстановка по Ctrl+C...")

    except Exception as exc:
        print(f"\n[КРИТИЧНО] Аварийная остановка: {exc!r}", flush=True)
        raise

    finally:
        save_journal(journal_df, JOURNAL_FILE)
        write_active_state(active, active_strategies, balance, MAX_RISK_PCT, JOURNAL_DIR)
        try:
            mt5.shutdown()
        except Exception:
            pass
        print("Журнал и состояние сохранены. Терминал отключён.")
