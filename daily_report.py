"""Генерация ежедневного отчёта эффективности стратегий (daily report).

Источники:
- strategy_registry.csv — маппинг magic → параметры стратегии
- mt5.history_deals_get(from, to) — фактические сделки и P&L

Метрики на стратегию:
- trades, profit, gross_profit, gross_loss, profit_factor, win_rate
- avg_profit, volume, best, worst, open_positions, conflict

Вывод:
- journals/reports/daily_YYYY-MM-DD.csv — полная таблица
- journals/reports/daily_YYYY-MM-DD_summary.csv — сводка по type + итог дня
- консоль: топ-5 стратегий дня + итог
"""
import os
import csv
import datetime
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

from config import RiskParams


def _reports_dir():
    """Путь к папке отчётов."""
    base = os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(base, 'journals', 'reports')
    os.makedirs(d, exist_ok=True)
    return d


def _registry_path():
    """Путь к реестру стратегий."""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'journals', 'strategy_registry.csv')


def _load_registry():
    """Загрузить реестр стратегий: magic → record."""
    path = _registry_path()
    if not os.path.exists(path):
        return {}
    
    registry = {}
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            magic = int(row['magic'])
            registry[magic] = {
                'symbol': row['symbol'],
                'type': row['type'],
                'param_key': row['param_key'],
                'parabolic_max': row.get('parabolic_max', ''),
                'activated_at': row.get('activated_at', ''),
                'deactivated_at': row.get('deactivated_at', ''),
                'conflict': int(row.get('conflict', 0)),
            }
    return registry


def _get_day_deals(date):
    """Получить все deals за календарный день [00:00, 23:59:59]."""
    start = datetime.datetime(date.year, date.month, date.day, 0, 0, 0)
    end = datetime.datetime(date.year, date.month, date.day, 23, 59, 59)
    
    deals = mt5.history_deals_get(start, end)
    if not deals:
        return []
    
    return list(deals)


def _aggregate_by_position(deals):
    """Сгруппировать deals по position_id, посчитать P&L позиции."""
    positions = {}
    for deal in deals:
        if deal.entry == mt5.DEAL_ENTRY_OUT:
            pos_id = deal.position_id
            if pos_id not in positions:
                positions[pos_id] = {
                    'magic': deal.magic,
                    'symbol': deal.symbol,
                    'time': deal.time,
                    'profit': 0.0,
                    'commission': 0.0,
                    'swap': 0.0,
                    'fee': 0.0,
                    'volume': 0.0,
                }
            positions[pos_id]['profit'] += deal.profit
            positions[pos_id]['commission'] += deal.commission
            positions[pos_id]['swap'] += deal.swap
            positions[pos_id]['fee'] += deal.fee
            positions[pos_id]['volume'] += deal.volume
    
    # Итоговый P&L = profit + commission + swap + fee
    for pos_id, pos in positions.items():
        pos['net_profit'] = pos['profit'] + pos['commission'] + pos['swap'] + pos['fee']
    
    return positions


def _count_open_positions(date, registry):
    """Посчитать открытые позиции по стратегиям на начало дня."""
    positions = mt5.positions_get()
    if not positions:
        return {}
    
    open_by_magic = {}
    for pos in positions:
        # Проверяем, что позиция открыта ДО начала дня или в начале дня
        if pos.time < datetime.datetime(date.year, date.month, date.day).timestamp():
            magic = pos.magic
            if magic not in open_by_magic:
                open_by_magic[magic] = 0
            open_by_magic[magic] += 1
    
    return open_by_magic


def _calc_strategy_metrics(positions, registry, open_positions):
    """Посчитать метрики для каждой стратегии."""
    # Группируем позиции по magic
    by_magic = {}
    for pos_id, pos in positions.items():
        magic = pos['magic']
        if magic not in by_magic:
            by_magic[magic] = []
        by_magic[magic].append(pos)
    
    metrics = []
    for magic, pos_list in by_magic.items():
        record = registry.get(magic)
        
        if record:
            symbol = record['symbol']
            stype = record['type']
            param_key = record['param_key']
            parabolic_max = record['parabolic_max']
            conflict = record['conflict']
        else:
            symbol = 'unknown'
            stype = 'manual/other'
            param_key = '-'
            parabolic_max = ''
            conflict = 0
        
        # Метрики
        trades = len(pos_list)
        profits = [p['net_profit'] for p in pos_list]
        profit = sum(profits)
        gross_profit = sum(p for p in profits if p > 0)
        gross_loss = sum(p for p in profits if p < 0)
        wins = sum(1 for p in profits if p > 0)
        win_rate = wins / trades if trades > 0 else 0
        avg_profit = profit / trades if trades > 0 else 0
        volume = sum(p['volume'] for p in pos_list)
        best = max(profits) if profits else 0
        worst = min(profits) if profits else 0
        
        if gross_loss == 0:
            pf = float('inf') if gross_profit > 0 else 0
            pf_str = '∞' if pf == float('inf') else '0'
        else:
            pf = gross_profit / abs(gross_loss)
            pf_str = f"{pf:.2f}"
        
        # Open positions
        open_count = open_positions.get(magic, 0)
        
        metrics.append({
            'magic': magic,
            'symbol': symbol,
            'type': stype,
            'param_key': param_key,
            'parabolic_max': parabolic_max,
            'trades': trades,
            'profit': round(profit, 2),
            'gross_profit': round(gross_profit, 2),
            'gross_loss': round(gross_loss, 2),
            'profit_factor': pf_str,
            'win_rate': round(win_rate * 100, 1),
            'avg_profit': round(avg_profit, 2),
            'volume': round(volume, 2),
            'best': round(best, 2),
            'worst': round(worst, 2),
            'open_positions': open_count,
            'conflict': conflict,
        })
    
    # Сортировка по profit desc
    metrics.sort(key=lambda x: x['profit'], reverse=True)
    return metrics


def _write_csv(date, metrics):
    """Записать full report в CSV."""
    reports_dir = _reports_dir()
    date_str = date.strftime('%Y-%m-%d')
    csv_file = os.path.join(reports_dir, f'daily_{date_str}.csv')
    
    fieldnames = ['symbol', 'type', 'param_key', 'parabolic_max', 'magic',
                  'trades', 'profit', 'gross_profit', 'gross_loss', 'profit_factor',
                  'win_rate', 'avg_profit', 'volume', 'best', 'worst',
                  'open_positions', 'conflict']
    
    with open(csv_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(metrics)
    
    return csv_file


def _write_summary(date, metrics):
    """Записать summary report в CSV (агрегаты по type + итог дня)."""
    reports_dir = _reports_dir()
    date_str = date.strftime('%Y-%m-%d')
    csv_file = os.path.join(reports_dir, f'daily_{date_str}_summary.csv')
    
    # Агрегаты по type
    by_type = {}
    total_profit = 0
    total_trades = 0
    
    for m in metrics:
        stype = m['type']
        if stype not in by_type:
            by_type[stype] = {'trades': 0, 'profit': 0, 'gross_profit': 0, 'gross_loss': 0, 'wins': 0}
        by_type[stype]['trades'] += m['trades']
        by_type[stype]['profit'] += m['profit']
        by_type[stype]['gross_profit'] += m['gross_profit']
        by_type[stype]['gross_loss'] += m['gross_loss']
        if m['profit'] > 0:
            by_type[stype]['wins'] += m['trades']
        total_profit += m['profit']
        total_trades += m['trades']
    
    summary = []
    for stype, agg in sorted(by_type.items(), key=lambda x: x[1]['profit'], reverse=True):
        trades = agg['trades']
        profit = round(agg['profit'], 2)
        gross_profit = round(agg['gross_profit'], 2)
        gross_loss = round(agg['gross_loss'], 2)
        win_rate = round(agg['wins'] / trades * 100, 1) if trades > 0 else 0
        
        if gross_loss == 0:
            pf_str = '∞' if gross_profit > 0 else '0'
        else:
            pf = gross_profit / abs(gross_loss)
            pf_str = f"{pf:.2f}"
        
        summary.append({
            'type': stype,
            'trades': trades,
            'profit': profit,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'profit_factor': pf_str,
            'win_rate': win_rate,
        })
    
    # Итог дня
    summary.append({
        'type': 'TOTAL',
        'trades': total_trades,
        'profit': round(total_profit, 2),
        'gross_profit': round(sum(s['gross_profit'] for s in summary), 2),
        'gross_loss': round(sum(s['gross_loss'] for s in summary), 2),
        'profit_factor': '',
        'win_rate': '',
    })
    
    fieldnames = ['type', 'trades', 'profit', 'gross_profit', 'gross_loss', 'profit_factor', 'win_rate']
    
    with open(csv_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary)
    
    return csv_file


def generate_daily_report(date=None):
    """Сгенерировать daily report за указанную дату.
    
    Args:
        date: datetime.date — если None, берётся yesterday.
    
    Returns:
        dict с путями к файлам отчётов или None.
    """
    if date is None:
        date = datetime.date.today() - datetime.timedelta(days=1)
    
    print(f"\n{'═' * 60}")
    print(f"  DAILY REPORT: {date}")
    print(f"{'═' * 60}")
    
    # 1. Загружаем реестр
    registry = _load_registry()
    print(f"  Реестр: {len(registry)} стратегий")
    
    # 2. Получаем deals за день
    deals = _get_day_deals(date)
    print(f"  Deals за день: {len(deals)}")
    
    if not deals:
        print(f"  ⚠️  Нет сделок — пустой отчёт")
        # Всё равно создаём пустой отчёт
        metrics = []
    else:
        # 3. Агрегируем по position_id
        positions = _aggregate_by_position(deals)
        print(f"  Закрытые позиции: {len(positions)}")
        
        # 4. Считаем открытые позиции на начало дня
        open_positions = _count_open_positions(date, registry)
        
        # 5. Считаем метрики
        metrics = _calc_strategy_metrics(positions, registry, open_positions)
    
    # 6. Пишем CSV
    full_csv = _write_csv(date, metrics)
    summary_csv = _write_summary(date, metrics)
    
    # 7. Консоль: топ-5 + итог
    print(f"\n  {'─' * 50}")
    print(f"  ТОП-5 СТРАТЕГИЙ ДНЯ")
    print(f"  {'─' * 50}")
    
    top5 = metrics[:5] if metrics else []
    for i, m in enumerate(top5, 1):
        profit_str = f"{m['profit']:+,.2f}"
        print(f"    {i}. {m['symbol']} {m['type']} {m['param_key']}")
        print(f"       trades={m['trades']} profit={profit_str} PF={m['profit_factor']} WR={m['win_rate']}%")
    
    total_profit = sum(m['profit'] for m in metrics)
    total_trades = sum(m['trades'] for m in metrics)
    print(f"  {'─' * 50}")
    print(f"  ИТОГО ДНЯ: trades={total_trades} profit={total_profit:+,.2f}")
    print(f"  {'═' * 60}\n")
    
    return {
        'full_csv': full_csv,
        'summary_csv': summary_csv,
        'metrics': metrics,
        'total_profit': total_profit,
            
                
                
                
                
                
                
                
            
        'total_trades': total_trades,
    }


def generate_missing_reports(start_date, end_date):
    """Сгенерировать все пропущенные daily отчёты за период.
    
    Args:
        start_date: datetime.date
        end_date: datetime.date
    
    Returns:
        list сгенерированных дат.
    """
    reports_dir = _reports_dir()
    generated = []
    
    current = start_date
    while current <= end_date:
        date_str = current.strftime('%Y-%m-%d')
        full_csv = os.path.join(reports_dir, f'daily_{date_str}.csv')
        
        if not os.path.exists(full_csv):
            print(f"  → Генерация пропущенного отчёта: {date_str}")
            result = generate_daily_report(current)
            if result:
                generated.append(current)
        
        current += datetime.timedelta(days=1)
    
    if generated:
        print(f"  ✅ Сгенерировано {len(generated)} пропущенных отчётов")
    else:
        print(f"  ✅ Нет пропущенных отчётов")
    
    return generated


def get_dashboard_data(days_back=30, manage_connection=True):
    """Единственная точка входа для дэшборда — собирает все данные из MT5.

    Args:
        days_back: сколько дней истории сделок загружать.
        manage_connection: True — функция сама делает mt5.shutdown()/initialize()
            и закрывает подключение в finally (режим дэшборда). False — вызывающий
            уже держит подключение к MT5 (режим main.py), функция его не трогает.

    Returns:
        dict с ключами:
        - 'balance': float — текущий баланс
        - 'equity': float — текущая equity
        - 'quota': float — квота риска (balance * 0.05)
        - 'updated': str — время обновления (ISO format)
        - 'trades_df': DataFrame — все сделки за период (только наш magic)
        - 'active_strategies': list — активные стратегии с позициями
        - 'total_trades': int — кол-во сделок за период
        - 'total_profit': float — суммарный PnL за период
    """
    # MAGIC_BASE = 770000 — все наши стратегии используют magic >= 770000
    # make_magic (strategy_engine.py) = 770000 + hash % 100000 → диапазон [770000, 869999]
    OUR_MAGIC_MIN = 770000
    OUR_MAGIC_MAX = OUR_MAGIC_MIN + 100000 - 1  # 869999

    # Наши символы имеют суффикс rfd — фильтруем по ним
    OUR_SYMBOLS_SUFFIX = 'rfd'

    # 1. Подключение к MT5
    if manage_connection: mt5.shutdown()
    if manage_connection and not mt5.initialize():
        print(f"  ⚠️  MT5 init failed: {mt5.last_error()}")
        return None

    try:
        # 2. Баланс и equity
        acc = mt5.account_info()
        if acc is None:
            print("  ⚠️  Не удалось получить информацию о счёте")
            return None

        balance = acc.balance
        equity = acc.equity
        quota = balance *  RiskParams.max_risk_pct  # MAX_RISK_PCT = 0.05

        # 3. История сделок — от max(1 сентября 2026, today - days_back)
        date_to = datetime.datetime.now() + datetime.timedelta(hours=6)  # запас: часы хоста могут отставать от сервера UTC+3
        date_from = max(datetime.datetime(2026, 9, 1), date_to - datetime.timedelta(days=days_back))

        n_deals_raw = 0
        n_deals_ours = 0
        deals = mt5.history_deals_get(date_from, date_to)
        if deals is None or len(deals) == 0:
            trades_df = pd.DataFrame()
        else:
            trades_df = pd.DataFrame([d._asdict() for d in deals])
            n_deals_raw = len(trades_df)

            # Фильтр: только торговые сделки
            type_map = {
                mt5.DEAL_TYPE_BUY: 'buy',
                mt5.DEAL_TYPE_SELL: 'sell',
            }
            trades_df['type'] = trades_df['type'].map(type_map)
            trades_df = trades_df[trades_df['type'].isin(['buy', 'sell'])]

            # Исключаем балансовые операции
            trades_df = trades_df[trades_df['entry'] != mt5.DEAL_ENTRY_OUT_BY]

            # 🔑 ФИЛЬТР ПО MAGIC — только наши сделки (>= 770000)
            trades_df['magic'] = trades_df['magic'].fillna(0).astype(int)
            trades_df = trades_df[(trades_df['magic'] >= OUR_MAGIC_MIN) & (trades_df['magic'] <= OUR_MAGIC_MAX)]

            # 🔑 ФИЛЬТР ПО СИМВОЛУ — только наши символы с суффиксом rfd
            trades_df = trades_df[trades_df['symbol'].str.endswith(OUR_SYMBOLS_SUFFIX, na=False)]
            n_deals_ours = len(trades_df)

            # 🔑 Привязка сделок к стратегиям: magic → (strategy_type, param_key)
            # ПРИМЕЧАНИЕ: фильтр по comment намеренно удалён (полная выдача).
            registry = _load_registry()
            trades_df['strategy_type'] = trades_df['magic'].map(
                lambda m: registry[m].get('type', '?') if m in registry else '?'
            )
            trades_df['param_key'] = trades_df['magic'].map(
                lambda m: registry[m].get('param_key', '?') if m in registry else '?'
            )
            # Отсев по comment убран: закрывающие сделки идут с comment='close'
            # и несут весь PnL; фильтруем только magic + rfd-суффикс символa.
                
                
            
            
            
            
            # Исключаем сделки без атрибуции к стратегии (открыты до имёнования) — шли как '?'
            trades_df = trades_df[trades_df['strategy_type'] != '?'].copy()
            print(f"  [DASHBOARD] Deals: {len(trades_df)} (magic [770000, 869999] + rfd)")

            # PnL нетто
            trades_df['profit_net'] = trades_df['profit'] + trades_df['commission'] + trades_df['swap']

            # Timestamp
            trades_df['timestamp'] = pd.to_datetime(trades_df['time'], unit='s')

            # Сортировка
            trades_df = trades_df.sort_values('timestamp').reset_index(drop=True)

            # ── Закрытые сделки: одна строка на позицию (вход+выход) ──
            # Открытые позиции (без DEAL_ENTRY_OUT) исключаются — их можно взять
            # отдельно из MT history (positions_get).
            trades_df['position_id'] = trades_df['position_id'].astype(str)
            closed_ids = trades_df.loc[trades_df['entry'] == mt5.DEAL_ENTRY_OUT, 'position_id']
            trades_df = trades_df[trades_df['position_id'].isin(closed_ids)].copy()
            agg = trades_df.sort_values('timestamp').groupby('position_id').agg(
                symbol=('symbol', 'first'),
                strategy_type=('strategy_type', 'first'),
                param_key=('param_key', 'first'),
                type=('type', 'first'),
                entry=('entry', 'max'),
                volume=('volume', 'first'),
                price=('price', 'last'),
                profit=('profit', 'sum'),
                commission=('commission', 'sum'),
                swap=('swap', 'sum'),
                profit_net=('profit_net', 'sum'),
                magic=('magic', 'first'),
                timestamp=('timestamp', 'max'),
                time=('time', 'max'),
            ).reset_index()
            trades_df = agg.sort_values('timestamp').reset_index(drop=True)
            # DEBUG: разбивка P&L Today (позиции закрытые сегодня, независимо от даты открытия)
            if 'time' in trades_df.columns:
                _off = datetime.timedelta(hours=3)  # торговый сервер AlfaForex = UTC+3
                _tu = pd.to_datetime(trades_df['time'], unit='s', utc=True) + _off
                _ser_today = (pd.Timestamp.now('UTC') + _off).date()
                tm = _tu.dt.date == _ser_today
                tm_utc = trades_df['timestamp'].dt.date == datetime.datetime.now().date()
                
                print(f"  [DASHBOARD] Окно: {len(trades_df)} поз., PnL_всего={trades_df['profit_net'].sum():+.2f} | TODAY(server+3)={int(tm.sum())} поз., PnL={trades_df.loc[tm, 'profit_net'].sum():+.2f} | TODAY(host)={int(tm_utc.sum())} поз., PnL={trades_df.loc[tm_utc, 'profit_net'].sum():+.2f}", flush=True)
                print(f"  [DASHBOARD]   последнее закрытие в данных: {pd.to_datetime(trades_df['time'].max(), unit='s')}", flush=True)
                    
                      

        # 4. Активные стратегии (из реестра + текущие позиции)
        registry = _load_registry()
        positions = mt5.positions_get()

        active_strategies = []
        if positions:
            for pos in positions:
                magic = pos.magic
                record = registry.get(magic)

                if record:
                    stype = record['type']
                    param_key = record['param_key']
                    parabolic_max = record.get('parabolic_max', '')
                else:
                    stype = 'unknown'
                    param_key = '-'
                    parabolic_max = ''

                active_strategies.append({
                    'symbol': pos.symbol,
                    'type': stype,
                    'param_key': param_key,
                    'parabolic_max': parabolic_max if parabolic_max else None,
                    'magic': magic,
                    'has_position': True,
                    'lot': pos.volume,
                    'entry_price': pos.price_open,
                    'sl_points': None,
                    'tp_points': None,
                    'score': 0,
                    'profit': 0,
                    'profit_factor': 0,
                    'win_rate': 0,
                    'n_trades': 0,
                })

        # 5. Итоги
        total_trades = len(trades_df)
        total_profit = float(trades_df['profit_net'].sum()) if not trades_df.empty else 0.0

        return {
            'balance': balance,
            'equity': equity,
            'quota': quota,
            'updated': datetime.datetime.now().isoformat(),
            'trades_df': trades_df,
            'active_strategies': active_strategies,
            'total_trades': total_trades,
            'total_profit': total_profit,
            'dash_stats': {
                'window_from': date_from.isoformat(),
                'window_to': date_to.isoformat(),
                'days_back': days_back,
                'n_deals_raw': n_deals_raw,
                'n_deals_ours': n_deals_ours,
                'n_closed_positions': len(trades_df),
                'n_open_positions': len(positions) if positions else 0,
            },
        }

    finally:
        if manage_connection: mt5.shutdown()
