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
    _normalize_volume, _position_profit, DEFAULT_LOT,
    get_positions, positions_total, check_margin_available,
    get_stops_levels, validate_stops, check_position_limits,
    check_daily_loss_limit, check_equity_stop, realtime_quota_recalc
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
    elif stype in ('macd_cross', 'rsi_rev', 'bollinger', 'ema_cross', 'rsi_div', 'ichimoku'):
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
    k = r['param_key']
    if stype == 'parabolic':
        return f"{pair}/SAR s{k}"
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
            key = (sym, stype, r['param_key'], r.get('parabolic_max', 0.2))
        else:
            key = (sym, stype, r['param_key'])

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
        writer.writerow(['rank', 'symbol', 'type', 'param_key', 'parabolic_max',
                         'sl_points', 'tp_points',
                         'profit', 'pf', 'mdd', 'win_rate', 'sharpe',
                         'recovery', 'score', 'top'])
        for i, r in enumerate(all_results):
            is_active = any(
                s['symbol'] == r['symbol'] and s['param_key'] == r['param_key']
                and s['sl_points'] == r['sl_points'] and s['tp_points'] == r['tp_points']
                and s.get('type', 'stoch') == r.get('type', 'stoch')
                and s.get('parabolic_max') == r.get('parabolic_max')
                for s in top_strats
            )
            pair = r['symbol'].replace('rfd', '')
            stype = r.get('type', 'stoch')
            pmax = r.get('parabolic_max')
            pmax_str = f"{pmax:.2f}" if pmax is not None else ""
            writer.writerow([i+1, pair, stype, r['param_key'], pmax_str,
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
            s['symbol'] == r['symbol'] and s['param_key'] == r['param_key']
            and s['sl_points'] == r['sl_points'] and s['tp_points'] == r['tp_points']
            and s.get('type', 'stoch') == r.get('type', 'stoch')
            and s.get('parabolic_max') == r.get('parabolic_max')
            for s in top_strats
        ) else ""
        stype = r.get('type', 'stoch')
        k_or_step = r['param_key']
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
        key = strategy_key(r['symbol'], r['param_key'], r.get('type', 'stoch'),
                           r.get('parabolic_max'))
        strat = active_strategies.get(key, {})
        has_position = strat.get('position') is not None
        state['strategies'].append({
            'symbol': r['symbol'],
            'type': r.get('type', 'stoch'),
            'param_key': r.get('param_key', '-'),
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


# ═══ РЕЕСТР СТРАТЕГИЙ ═══
def _registry_path():
    """Путь к файлу реестра стратегий."""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'journals', 'strategy_registry.csv')


def _ensure_registry():
    """Создать файл реестра с заголовком, если не существует."""
    path = _registry_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['magic', 'symbol', 'type', 'param_key', 'parabolic_max',
                             'activated_at', 'deactivated_at', 'conflict'])


def _register_strategy(magic, symbol, stype, param_key, parabolic_max, activated_at):
    """Добавить/обновить запись в реестре."""
    path = _registry_path()
    _ensure_registry()
    
    # Проверяем, есть ли уже такая запись
    existing = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row['magic']) == magic and row['symbol'] == symbol:
                # Параметры совпали — не дублируем
                if (row['type'] == stype and row['param_key'] == param_key and
                        str(row.get('parabolic_max', '')) == str(parabolic_max)):
                    return  # Уже есть
                # Параметры изменились — обновляем
                existing.append(row)
                break
    
    if not existing:
        # Новая стратегия — добавляем
        with open(path, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([magic, symbol, stype, param_key,
                             f"{parabolic_max:.2f}" if parabolic_max is not None else '',
                             activated_at, '', 0])


def _deregister_strategy(magic, symbol, deactivated_at):
    """Пометить стратегию как деактивированную."""
    path = _registry_path()
    if not os.path.exists(path):
        return
    
    rows = []
    updated = False
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row['magic']) == magic and row['symbol'] == symbol and not row['deactivated_at']:
                row['deactivated_at'] = deactivated_at
                updated = True
            rows.append(row)
    
    if updated:
        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)


# ═══ СИНХРОНИЗАЦИЯ АКТИВНЫХ СТРАТЕГИЙ ═══
def sync_active_strategies(top_results, now, symbol_data, active_strategies, close_order_fn,
                           get_deal_exit_price_fn, record_trade_fn, strategy_key_fn,
                           make_magic_fn, MAGIC_BASE, TOP_N):
    """Открывает позиции для новых топ-N, закрывает те, что выпали из топа."""
    # Текущие ключи топа
    top_keys = set()
    for r in top_results:
        stype = r.get('type', 'stoch')
        param = r['param_key']
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
        _deregister_strategy(s['magic'], s['symbol'], now.isoformat())
        del active_strategies[key]

    # Добавляем новые из топа
    existing_magics = {s['magic'] for s in active_strategies.values()}
    for r in top_results:
        stype = r.get('type', 'stoch')
        param = r['param_key']
        extra = r.get('parabolic_max')
        key = strategy_key_fn(r['symbol'], param, stype, extra)
        if key not in active_strategies:
            magic = make_magic_fn(r['symbol'], stype, param, extra)
            if magic in existing_magics:
                print(f"  -> [WARN] Коллизия magic {magic} у {key} — стратегия пропущена")
                continue
            strat_dict = {
                'symbol': r['symbol'],
                'param_key': param,
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
            # MACD Cross-specific params
            elif stype == 'macd_cross':
                k = param  # "mf12_ms26_sig9"
                for p in k.split('_'):
                    if p.startswith('mf'):
                        strat_dict['macd_fast'] = int(p[2:])
                    elif p.startswith('ms'):
                        strat_dict['macd_slow'] = int(p[2:])
                    elif p.startswith('sig'):
                        strat_dict['macd_signal'] = int(p[3:])
            # RSI Reversal-specific params
            elif stype == 'rsi_rev':
                k = param  # "rp14_ros30_rob70"
                for p in k.split('_'):
                    if p.startswith('rp'):
                        strat_dict['rsi_period'] = int(p[2:])
                    elif p.startswith('ros'):
                        strat_dict['rsi_oversold'] = int(p[3:])
                    elif p.startswith('rob'):
                        strat_dict['rsi_overbought'] = int(p[3:])
            # Bollinger-specific params
            elif stype == 'bollinger':
                k = param  # "bp20_bs2"
                for p in k.split('_'):
                    if p.startswith('bp'):
                        strat_dict['bb_period'] = int(p[2:])
                    elif p.startswith('bs'):
                        strat_dict['bb_std'] = float(p[2:])
            # EMA Crossover-specific params
            elif stype == 'ema_cross':
                k = param  # "ef9_es21"
                for p in k.split('_'):
                    if p.startswith('ef'):
                        strat_dict['ema_fast'] = int(p[2:])
                    elif p.startswith('es'):
                        strat_dict['ema_slow'] = int(p[2:])
            # RSI Divergence-specific params
            elif stype == 'rsi_div':
                k = param  # "rp14_lb5_th0.50"
                for p in k.split('_'):
                    if p.startswith('rp'):
                        strat_dict['rsi_period'] = int(p[2:])
                    elif p.startswith('lb'):
                        strat_dict['lookback'] = int(p[2:])
                    elif p.startswith('th'):
                        strat_dict['threshold'] = float(p[2:])
            # Ichimoku-specific params
            elif stype == 'ichimoku':
                k = param  # "ten9_kij26"
                for p in k.split('_'):
                    if p.startswith('ten'):
                        strat_dict['tenkan'] = int(p[3:])
                    elif p.startswith('kij'):
                        strat_dict['kijun'] = int(p[3:])
            # Z-score reversion-specific params
            elif stype == 'zscore':
                k = param  # "sma20_z2.0"
                for p in k.split('_'):
                    if p.startswith('sma'):
                        strat_dict['sma_period'] = int(p[3:])
                    elif p.startswith('z'):
                        strat_dict['z_threshold'] = float(p[1:])
            # Autocorrelation momentum-specific params
            elif stype == 'autocorr':
                k = param  # "lag1_th0.30"
                for p in k.split('_'):
                    if p.startswith('lag'):
                        strat_dict['acf_lag'] = int(p[3:])
                    elif p.startswith('th'):
                        strat_dict['threshold'] = float(p[2:])
            # Hurst regime filter-specific params
            elif stype == 'hurst':
                k = param  # "win20_th0.60"
                for p in k.split('_'):
                    if p.startswith('win'):
                        strat_dict['window'] = int(p[3:])
                    elif p.startswith('th'):
                        strat_dict['trend_threshold'] = float(p[2:])
            # Linear Regression Channel-specific params
            elif stype == 'lrc':
                k = param  # "per20_std2.0"
                for p in k.split('_'):
                    if p.startswith('per'):
                        strat_dict['period'] = int(p[3:])
                    elif p.startswith('std'):
                        strat_dict['std_threshold'] = float(p[3:])
            # Percentile reversion-specific params
            elif stype == 'percentile':
                k = param  # "per20_l5_h95"
                for p in k.split('_'):
                    if p.startswith('per'):
                        strat_dict['period'] = int(p[3:])
                    elif p.startswith('l'):
                        strat_dict['pct_low'] = int(p[1:])
                    elif p.startswith('h'):
                        strat_dict['pct_high'] = int(p[1:])
            # Runs Test trend-specific params
            elif stype == 'runs':
                k = param  # "win20_th1.5"
                for p in k.split('_'):
                    if p.startswith('win'):
                        strat_dict['window'] = int(p[3:])
                    elif p.startswith('th'):
                        strat_dict['z_threshold'] = float(p[2:])
            # Cointegration pairs-specific params
            elif stype == 'coint':
                k = param  # "win20_th1.5"
                for p in k.split('_'):
                    if p.startswith('win'):
                        strat_dict['window'] = int(p[3:])
                    elif p.startswith('th'):
                        strat_dict['z_entry'] = float(p[2:])
            # Rolling Sharpe filter-specific params
            elif stype == 'sharpe':
                k = param  # "win20_th0.50"
                for p in k.split('_'):
                    if p.startswith('win'):
                        strat_dict['window'] = int(p[3:])
                    elif p.startswith('th'):
                        strat_dict['sharpe_entry'] = float(p[2:])
            # Skewness extreme-specific params
            elif stype == 'skewness':
                k = param  # "win20_th0.8"
                for p in k.split('_'):
                    if p.startswith('win'):
                        strat_dict['window'] = int(p[3:])
                    elif p.startswith('th'):
                        strat_dict['skew_entry'] = float(p[2:])
            # Bayesian trend update-specific params
            elif stype == 'bayesian':
                k = param  # "win20_th0.60"
                for p in k.split('_'):
                    if p.startswith('win'):
                        strat_dict['window'] = int(p[3:])
                    elif p.startswith('th'):
                        strat_dict['p_entry'] = float(p[2:])
            # Kurtosis spike-specific params
            elif stype == 'kurtosis':
                k = param  # "win20_th3.0"
                for p in k.split('_'):
                    if p.startswith('win'):
                        strat_dict['window'] = int(p[3:])
                    elif p.startswith('th'):
                        strat_dict['kurt_entry'] = float(p[2:])
            # Chi-square distribution-specific params
            elif stype == 'chi_square':
                k = param  # "win20_e0.05_x0.20"
                for p in k.split('_'):
                    if p.startswith('win'):
                        strat_dict['window'] = int(p[3:])
                    elif p.startswith('e'):
                        strat_dict['p_entry'] = float(p[1:])
                    elif p.startswith('x'):
                        strat_dict['p_exit'] = float(p[1:])
            active_strategies[key] = strat_dict
            existing_magics.add(magic)
            # ── Регистрируем новую стратегию ──
            _register_strategy(magic, r['symbol'], stype, param, extra, now.isoformat())
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
        'symbol': s['symbol'], 'param_key': s['param_key'],
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


def send_order(symbol, direction, lot, sl, tp, magic, comment, symbol_data,
               risk_params=None):
    """Отправить ордер с расширенной проверкой риск-менеджмента.
    
    Args:
        risk_params: dict с ключами:
            - check_margin: bool (по умолчанию True)
            - check_stops: bool (по умолчанию True)
            - min_sl_distance_points: int (по умолчанию 10)
            - max_sl_distance_points: int (по умолчанию 500)
    """
    if risk_params is None:
        risk_params = {}
    
    check_margin = risk_params.get('check_margin', True)
    check_stops = risk_params.get('check_stops', True)
    min_sl_dist = risk_params.get('min_sl_distance_points', 10)
    max_sl_dist = risk_params.get('max_sl_distance_points', 500)
    
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
    
    # ── Проверка 1: Free margin (пункт 2) ──
    if check_margin:
        entry_price = tick.ask if direction == 'long' else tick.bid
        sl_dist_points = abs(entry_price - sl) / info.point if info else 0
        margin_ok, margin_req, margin_free = check_margin_available(
            lot, symbol, entry_price, sl_dist_points
        )
        if not margin_ok:
            print(f"  -> [WARN] {symbol}: недостаточно margin (req={margin_req:.2f}, free={margin_free:.2f}) — ордер пропущен")
            return None
    
    # ── Проверка 2: Stops levels брокера (пункт 5) ──
    if check_stops:
        valid, reason, min_dist = validate_stops(sl, tp, tick.ask if direction == 'long' else tick.bid, symbol)
        if not valid:
            print(f"  -> [WARN] {symbol}: SL/TP отклонены ({reason}) — ордер пропущен")
            return None
        
        # Проверка минимального расстояния SL
        entry_price = tick.ask if direction == 'long' else tick.bid
        sl_distance_points = abs(entry_price - sl) / info.point if info else 0
        if sl_distance_points < min_sl_dist:
            print(f"  -> [WARN] {symbol}: SL слишком близко ({sl_distance_points:.0f} < {min_sl_dist} пуктов) — ордер пропущен")
            return None
        if sl_distance_points > max_sl_dist:
            print(f"  -> [WARN] {symbol}: SL слишком далеко ({sl_distance_points:.0f} > {max_sl_dist} пуктов) — ордер пропущен")
            return None
    
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
        elif result.retcode == mt5.TRADE_RETCODE_NOT_ENOUGH_MONEY:
            acc = mt5.account_info()
            print(f"  -> [WARN] Ордер {symbol} {direction}: не хватает денег (free={acc.margin_free if acc else 0:.2f})")
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
                         calc_macd_cross_fn=None, check_exit_macd_cross_fn=None,
                         check_entry_macd_cross_fn=None,
                         calc_rsi_reversal_fn=None, check_exit_rsi_reversal_fn=None,
                         check_entry_rsi_reversal_fn=None,
                         calc_bollinger_fn=None, check_exit_bollinger_fn=None,
                         check_entry_bollinger_fn=None,
                         calc_ema_crossover_fn=None, check_exit_ema_crossover_fn=None,
                         check_entry_ema_crossover_fn=None,
                         calc_rsi_divergence_fn=None, check_exit_rsi_divergence_fn=None,
                         check_entry_rsi_divergence_fn=None,
                         calc_ichimoku_fn=None, check_exit_ichimoku_fn=None,
                         check_entry_ichimoku_fn=None,
                         calc_zscore_fn=None, check_exit_zscore_fn=None, check_entry_zscore_fn=None,
                         calc_autocorrelation_fn=None, check_exit_autocorr_fn=None, check_entry_autocorr_fn=None,
                         calc_hurst_fn=None, check_exit_hurst_fn=None, check_entry_hurst_fn=None,
                         calc_lr_channel_fn=None, check_exit_lrc_fn=None, check_entry_lrc_fn=None,
                         calc_percentile_fn=None, check_exit_percentile_fn=None, check_entry_percentile_fn=None,
                         calc_runs_test_fn=None, check_exit_runs_fn=None, check_entry_runs_fn=None,
                         calc_cointegration_fn=None, check_exit_coint_fn=None, check_entry_coint_fn=None,
                         calc_rolling_sharpe_fn=None, check_exit_sharpe_fn=None, check_entry_sharpe_fn=None,
                         calc_skewness_fn=None, check_exit_skewness_fn=None, check_entry_skewness_fn=None,
                         calc_bayesian_trend_fn=None, check_exit_bayesian_fn=None, check_entry_bayesian_fn=None,
                         calc_kurtosis_fn=None, check_exit_kurtosis_fn=None, check_entry_kurtosis_fn=None,
                         calc_chi_square_fn=None, check_exit_chi_square_fn=None, check_entry_chi_square_fn=None,
                         risk_params=None, position_limits=None):
    """Проверяет сигналы для активных стратегий на закрытом баре.
    
    Args:
        risk_params: dict параметров риск-менеджмента (пропускается в send_order)
        position_limits: dict лимитов {'max_total': int, 'max_per_symbol': int}
    """
    if risk_params is None:
        risk_params = {}
    if position_limits is None:
        position_limits = {'max_total': 15, 'max_per_symbol': 3}
    
    # ── Проверка 1: Реальные позиции MT5 (пункт 1) ──
    # Собираем занятые (символ, тип) ИЗ РЕАЛЬНЫХ ПОЗИЦИЙ MT5
    occupied_by_symbol = {}
    real_positions = mt5.positions_get()
    if real_positions:
        for pos in real_positions:
            sym = pos.symbol
            if sym not in occupied_by_symbol:
                occupied_by_symbol[sym] = set()
            # Определяем тип по magic number
            for key, s in active_strategies.items():
                if pos.magic == s['magic']:
                    occupied_by_symbol[sym].add(s.get('type', 'stoch'))
                    break
            else:
                # Если magic не найден в active_strategies, считаем как 'unknown'
                occupied_by_symbol[sym].add('unknown')
    
    # ── Проверка 2: Лимиты позиций (пункт 3) ──
    current_counts = {sym: len(types) for sym, types in occupied_by_symbol.items()}
    limits_ok, limits_reason, limits_details = check_position_limits(
        current_counts,
        position_limits['max_total'],
        position_limits['max_per_symbol']
    )
    if not limits_ok:
        print(f"  -> [WARN] Лимиты позиций: {limits_reason}")

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
                df = calc_stochastic_fn(df, s['param_key'])
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
                        # Проверка лимитов
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and stype in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/{stype}")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is None:
                                pass
                            else:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist

                                comment = f"{s['symbol']}, K={s['param_key']}"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {
                                        'direction': entry_dir,
                                        'entry_price': entry,
                                        'entry_time': now,
                                        'ticket': ticket,
                                        'lot': s['lot'],
                                    }
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'parabolic':
                df = calc_parabolic_fn(df, s['param_key'], s.get('parabolic_max', 0.2))
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
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'parabolic' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/parabolic")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist

                                comment = f"{s['symbol']}, Step={s['param_key']}, Max={s.get('parabolic_max', 0.2)}"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {
                                        'direction': entry_dir,
                                        'entry_price': entry,
                                        'entry_time': now,
                                        'ticket': ticket,
                                        'lot': s['lot'],
                                    }
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'ma':
                df = calc_moving_average_fn(df, s['param_key'])
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
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'ma' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/ma")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist

                                comment = f"{s['symbol']}, MA={s['param_key']}"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {
                                        'direction': entry_dir,
                                        'entry_price': entry,
                                        'entry_time': now,
                                        'ticket': ticket,
                                        'lot': s['lot'],
                                    }
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
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'rf' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/rf")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist

                                comment = f"{s['symbol']}, RF {s.get('param_key', '')}"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {
                                        'direction': entry_dir,
                                        'entry_price': entry,
                                        'entry_time': now,
                                        'ticket': ticket,
                                        'lot': s['lot'],
                                    }
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
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'logreg' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/logreg")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist

                                comment = f"{s['symbol']}, LogReg {s.get('param_key', '')}"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {
                                        'direction': entry_dir,
                                        'entry_price': entry,
                                        'entry_time': now,
                                        'ticket': ticket,
                                        'lot': s['lot'],
                                    }
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'macd_cross':
                if calc_macd_cross_fn is None:
                    print(f"  -> [{key}] MACD-Cross — модуль не передан")
                    continue
                df = calc_macd_cross_fn(df, s.get('macd_fast', 12), s.get('macd_slow', 26), s.get('macd_signal', 9))
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['signal'].iloc[-2]
                curr_signal = df['signal'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_macd_cross_fn(prev_signal, curr_signal, s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_macd_cross_fn(prev_signal, curr_signal)
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'macd_cross' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/macd_cross")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None
                            
                            if entry is not None:
                                comment = f"{s['symbol']}, MACD-Cross"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'rsi_rev':
                if calc_rsi_reversal_fn is None:
                    print(f"  -> [{key}] RSI-Rev — модуль не передан")
                    continue
                df = calc_rsi_reversal_fn(df, s.get('rsi_period', 14), s.get('rsi_oversold', 30), s.get('rsi_overbought', 70))
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['signal'].iloc[-2]
                curr_signal = df['signal'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_rsi_reversal_fn(prev_signal, curr_signal, s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_rsi_reversal_fn(prev_signal, curr_signal)
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'rsi_rev' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/rsi_rev")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None
                            
                            if entry is not None:
                                comment = f"{s['symbol']}, RSI-Rev"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'bollinger':
                if calc_bollinger_fn is None:
                    print(f"  -> [{key}] Bollinger — модуль не передан")
                    continue
                df = calc_bollinger_fn(df, s.get('bb_period', 20), s.get('bb_std', 2), s.get('volume_period', 20))
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
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'bollinger' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/bollinger")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None
                            
                            if entry is not None:
                                comment = f"{s['symbol']}, Bollinger"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'ema_cross':
                if calc_ema_crossover_fn is None:
                    print(f"  -> [{key}] EMA — модуль не передан")
                    continue
                df = calc_ema_crossover_fn(df, s.get('ema_fast', 9), s.get('ema_slow', 21))
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
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'ema_cross' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/ema_cross")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None
                            
                            if entry is not None:
                                comment = f"{s['symbol']}, EMA"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'rsi_div':
                if calc_rsi_divergence_fn is None:
                    print(f"  -> [{key}] RSI-Div — модуль не передан")
                    continue
                df = calc_rsi_divergence_fn(df, s.get('rsi_period', 14), s.get('lookback', 5), s.get('threshold', 0.5))
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
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'rsi_div' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/rsi_div")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None
                            
                            if entry is not None:
                                comment = f"{s['symbol']}, RSI-Div"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'ichimoku':
                if calc_ichimoku_fn is None:
                    print(f"  -> [{key}] Ichimoku — модуль не передан")
                    continue
                df = calc_ichimoku_fn(df, s.get('tenkan', 9), s.get('kijun', 26), s.get('senkou_b', 52), s.get('displacement', 26))
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
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'ichimoku' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/ichimoku")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None
                            
                            if entry is not None:
                                comment = f"{s['symbol']}, Ichimoku"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'zscore':
                if calc_zscore_fn is None:
                    print(f"  -> [{key}] Zscore — модуль не передан")
                    continue
                df = calc_zscore_fn(df, s.get('sma_period', 30), s.get('z_threshold', 2.0))
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['zscore'].iloc[-2]
                curr_signal = df['zscore'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_zscore_fn(prev_signal, curr_signal, s.get('z_threshold', 2.0), s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_zscore_fn(prev_signal, curr_signal, s.get('z_threshold', 2.0))
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'zscore' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/zscore")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None

                            if entry is not None:
                                comment = f"{s['symbol']}, Zscore"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'autocorr':
                if calc_autocorrelation_fn is None:
                    print(f"  -> [{key}] Autocorr — модуль не передан")
                    continue
                df = calc_autocorrelation_fn(df, s.get('acf_lag', 3), s.get('threshold', 0.3))
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['acf'].iloc[-2]
                curr_signal = df['acf'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_autocorr_fn(prev_signal, curr_signal, s.get('threshold', 0.3), s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_autocorr_fn(prev_signal, curr_signal, s.get('threshold', 0.3))
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'autocorr' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/autocorr")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None

                            if entry is not None:
                                comment = f"{s['symbol']}, Autocorr"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'hurst':
                if calc_hurst_fn is None:
                    print(f"  -> [{key}] Hurst — модуль не передан")
                    continue
                df = calc_hurst_fn(df, s.get('window', 40), s.get('trend_threshold', 0.6))
                if df is None or len(df) < 2:
                    continue
                prev_trend = df['trend_up'].iloc[-2] if df['trend_up'].iloc[-2] else df['trend_down'].iloc[-2]
                curr_trend = df['trend_up'].iloc[-1] if df['trend_up'].iloc[-1] else df['trend_down'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_hurst_fn(prev_trend, curr_trend, s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_hurst_fn(prev_trend, curr_trend)
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'hurst' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/hurst")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None

                            if entry is not None:
                                comment = f"{s['symbol']}, Hurst"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'lrc':
                if calc_lr_channel_fn is None:
                    print(f"  -> [{key}] LRC — модуль не передан")
                    continue
                df = calc_lr_channel_fn(df, s.get('period', 30), s.get('std_threshold', 2.0))
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['lr_signal'].iloc[-2]
                curr_signal = df['lr_signal'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_lrc_fn(prev_signal, curr_signal, s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_lrc_fn(prev_signal, curr_signal)
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'lrc' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/lrc")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None

                            if entry is not None:
                                comment = f"{s['symbol']}, LRC"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'percentile':
                if calc_percentile_fn is None:
                    print(f"  -> [{key}] Percentile — модуль не передан")
                    continue
                df = calc_percentile_fn(df, s.get('period', 30), s.get('pct_low', 5), s.get('pct_high', 95))
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['percentile'].iloc[-2]
                curr_signal = df['percentile'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_percentile_fn(prev_signal, curr_signal, s.get('mid_pct', 50), s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_percentile_fn(prev_signal, curr_signal, s.get('pct_low', 5), s.get('pct_high', 95))
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'percentile' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/percentile")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None

                            if entry is not None:
                                comment = f"{s['symbol']}, Percentile"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'runs':
                if calc_runs_test_fn is None:
                    print(f"  -> [{key}] Runs — модуль не передан")
                    continue
                df = calc_runs_test_fn(df, s.get('window', 30), s.get('z_threshold', 1.96))
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['z_stat'].iloc[-2]
                curr_signal = df['z_stat'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_runs_fn(prev_signal, curr_signal, s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_runs_fn(prev_signal, curr_signal, s.get('z_threshold', 1.96))
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'runs' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/runs")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None

                            if entry is not None:
                                comment = f"{s['symbol']}, Runs"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'coint':
                if calc_cointegration_fn is None:
                    print(f"  -> [{key}] Coint — модуль не передан")
                    continue
                df = calc_cointegration_fn(df, s.get('window', 40), s.get('z_entry', 2.0))
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['spread_z'].iloc[-2]
                curr_signal = df['spread_z'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_coint_fn(prev_signal, curr_signal, s.get('z_exit', 0.0), s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_coint_fn(prev_signal, curr_signal, s.get('z_entry', 2.0))
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'coint' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/coint")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None

                            if entry is not None:
                                comment = f"{s['symbol']}, Coint"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'sharpe':
                if calc_rolling_sharpe_fn is None:
                    print(f"  -> [{key}] Sharpe — модуль не передан")
                    continue
                df = calc_rolling_sharpe_fn(df, s.get('window', 40), s.get('sharpe_entry', 0.5))
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['sharpe'].iloc[-2]
                curr_signal = df['sharpe'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_sharpe_fn(prev_signal, curr_signal, s.get('sharpe_exit', 0.0), s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_sharpe_fn(prev_signal, curr_signal, s.get('sharpe_entry', 0.5))
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'sharpe' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/sharpe")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None

                            if entry is not None:
                                comment = f"{s['symbol']}, Sharpe"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'skewness':
                if calc_skewness_fn is None:
                    print(f"  -> [{key}] Skewness — модуль не передан")
                    continue
                df = calc_skewness_fn(df, s.get('window', 30), s.get('skew_entry', 1.0))
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['skewness'].iloc[-2]
                curr_signal = df['skewness'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_skewness_fn(prev_signal, curr_signal, s.get('skew_exit', 0.3), s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_skewness_fn(prev_signal, curr_signal, s.get('skew_entry', 1.0), s.get('skew_exit', 0.3))
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'skewness' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/skewness")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None

                            if entry is not None:
                                comment = f"{s['symbol']}, Skewness"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'bayesian':
                if calc_bayesian_trend_fn is None:
                    print(f"  -> [{key}] Bayesian — модуль не передан")
                    continue
                df = calc_bayesian_trend_fn(df, s.get('window', 30), s.get('prior', 0.5), s.get('p_entry', 0.65))
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['p_trend'].iloc[-2]
                curr_signal = df['p_trend'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_bayesian_fn(prev_signal, curr_signal, s.get('p_exit', 0.5), s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_bayesian_fn(prev_signal, curr_signal, s.get('p_entry', 0.65))
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'bayesian' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/bayesian")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None

                            if entry is not None:
                                comment = f"{s['symbol']}, Bayesian"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'kurtosis':
                if calc_kurtosis_fn is None:
                    print(f"  -> [{key}] Kurtosis — модуль не передан")
                    continue
                df = calc_kurtosis_fn(df, s.get('window', 40), s.get('kurt_entry', 5.0))
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['kurtosis'].iloc[-2]
                curr_kurt = df['kurtosis'].iloc[-1]
                curr_sigma = df['sigma'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_kurtosis_fn(prev_signal, curr_kurt, s.get('kurt_exit', 3.0), s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_kurtosis_fn(prev_signal, curr_kurt, curr_sigma,
                                                        s.get('kurt_entry', 5.0), s.get('sigma_mult', 1.0))
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'kurtosis' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/kurtosis")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None

                            if entry is not None:
                                comment = f"{s['symbol']}, Kurtosis"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

            elif stype == 'chi_square':
                if calc_chi_square_fn is None:
                    print(f"  -> [{key}] ChiSq — модуль не передан")
                    continue
                df = calc_chi_square_fn(df, s.get('window', 30), s.get('p_entry', 0.05))
                if df is None or len(df) < 2:
                    continue
                prev_signal = df['chi2_pvalue'].iloc[-2]
                curr_signal = df['chi2_pvalue'].iloc[-1]
                if s['position'] is not None:
                    if _handle_position_gone(key, s, now, symbol_data, get_deal_exit_price_fn,
                                             _record_close_fn, record_trade_fn):
                        continue
                    if check_exit_chi_square_fn(prev_signal, curr_signal, s.get('p_exit', 0.2), s['position']['direction']):
                        exit_price = close_order_fn(s['symbol'], s['position']['ticket'],
                                                    s['position']['direction'], s['magic'], symbol_data)
                        if exit_price is not None:
                            _record_close_fn(key, s, now, exit_price, 'signal', symbol_data, record_trade_fn,
                                             journal_df, JOURNAL_FILE)
                if s['position'] is None:
                    entry_dir = check_entry_chi_square_fn(prev_signal, curr_signal, s.get('p_entry', 0.05))
                    if entry_dir:
                        if not limits_ok:
                            print(f"  -> [{key}] Пропущен вход: лимиты позиций — {limits_reason}")
                        elif s['symbol'] in occupied_by_symbol and 'chi_square' in occupied_by_symbol[s['symbol']]:
                            print(f"  -> [{key}] Пропущен вход: уже есть позиция {s['symbol']}/chi_square")
                        elif s['symbol'] in occupied_by_symbol and len(occupied_by_symbol[s['symbol']]) >= position_limits['max_per_symbol']:
                            print(f"  -> [{key}] Пропущен вход: {position_limits['max_per_symbol']} позиций на {s['symbol']}")
                        else:
                            tick = mt5.symbol_info_tick(s['symbol'])
                            if tick is not None:
                                sl_dist = s['sl_points'] * info.point
                                tp_dist = s['tp_points'] * info.point
                                if entry_dir == 'long':
                                    entry, sl, tp = tick.ask, tick.ask - sl_dist, tick.ask + tp_dist
                                else:
                                    entry, sl, tp = tick.bid, tick.bid + sl_dist, tick.bid - tp_dist
                            else:
                                entry = sl = tp = None

                            if entry is not None:
                                comment = f"{s['symbol']}, ChiSq"
                                ticket = send_order_fn(s['symbol'], entry_dir, s['lot'],
                                                       sl, tp, s['magic'], comment, symbol_data,
                                                       risk_params=risk_params)
                                if ticket is not None:
                                    s['position'] = {'direction': entry_dir, 'entry_price': entry,
                                                     'entry_time': now, 'ticket': ticket, 'lot': s['lot']}
                                    print(f"  -> [{key}] Открыт {entry_dir.upper()}: entry={entry:.{digits}f}, lot={s['lot']}")

        except Exception as e:
            print(f"\n[WARN] Ошибка стратегии {key}: {e!r}", flush=True)
            continue
