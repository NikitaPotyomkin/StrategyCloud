"""Управление рисками: метрики, скоринг, распределение лотов."""
import math
import numpy as np
import MetaTrader5 as mt5
import datetime


# ═══ ВЫЧИСЛИТЕЛЬНЫЙ БЮДЖЕТ ═══
MAX_COMBOS_PER_STRATEGY = 20_000


def _combo(n1, n2=1, n3=1, n4=1, n5=1, n6=1):
    """Произведение длин списков."""
    return n1 * n2 * n3 * n4 * n5 * n6


def check_integration_budget(budgets, SYMBOLS):
    """Проверить бюджет при интеграции новых стратегий.

    Args:
        budgets: dict {strategy_name: combos} комбинаций на 1 символ
        SYMBOLS: список символов

    Returns:
        dict {strategy_name: (budget, limit, violated)}
    """
    total = sum(budgets.values())
    n_symbols = len(SYMBOLS)
    total_all_symbols = total * n_symbols

    print(f"\n{'═' * 70}")
    print(f"  ВЫЧИСЛИТЕЛЬНЫЙ БЮДЖЕТ (лимит {MAX_COMBOS_PER_STRATEGY:,} на стратегию)")
    print(f"{'═' * 70}")

    results = {}
    violations = []
    for name, budget in sorted(budgets.items(), key=lambda x: x[1], reverse=True):
        violated = budget > MAX_COMBOS_PER_STRATEGY
        results[name] = (budget, MAX_COMBOS_PER_STRATEGY, violated)
        if violated:
            excess = budget - MAX_COMBOS_PER_STRATEGY
            violations.append((name, budget, excess))

    for name, (budget, limit, violated) in results.items():
        pct = budget / limit * 100 if limit > 0 else 0
        status = ""
        if violated:
            status = " 🔴 ПРЕРЫВАНИЕ"
        elif budget > limit * 0.8:
            status = " 🟡 близко"
        print(f"{name:<14} | {budget:>8,} | {pct:>5.1f}% | {status}")

    print(f"{'─' * 70}")
    print(f"  ИТОГО: {total:>8,} комб./символ | {total_all_symbols:>10,} комб. ({n_symbols} символов)")

    if violations:
        print(f"\n  ⛔ {len(violations)} стратегий превысили лимит {MAX_COMBOS_PER_STRATEGY:,}:")
        for name, budget, excess in violations:
            print(f"    {name}: {budget:,} > {MAX_COMBOS_PER_STRATEGY:,} (+{excess:,} комб.)")
    else:
        print(f"\n  ✅ Все стратегии в пределах лимита {MAX_COMBOS_PER_STRATEGY:,}.")
    print(f"{'═' * 70}\n")

    return results


# ═══ КОНСТАНТЫ ОЦЕНКИ ═══
SCORE_WEIGHTS = {
    'profit': 0.35,
    'profit_factor': 0.25,
    'win_rate': 0.15,
    'sharpe': 0.15,
    'recovery': 0.10,
}
DEFAULT_PROFIT_SCALE = 1000.0
DEFAULT_LOT = 0.01

_WARNED_MISSING_INFO = set()


def _warn_missing_info(symbol, where):
    if symbol not in _WARNED_MISSING_INFO:
        _WARNED_MISSING_INFO.add(symbol)
        print(f"  ⚠ {symbol}: symbol_info недоступен ({where}) — пропуск", flush=True)


def json_default(obj):
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


# ═══ ДЕНЕЖНЫЕ РАСЧЁТЫ ЧЕРЕЗ MT5 API ═══

def _sl_money_per_lot(symbol, info, sl_points):
    """Риск на 1 лот при срабатывании SL — через order_calc_profit.

    Возвращает абсолютную величину убытка в валюте счёта.
    Фоллбэк — старый метод через tick_value/tick_size.
    """
    if sl_points <= 0:
        return 0.0
    point = getattr(info, 'point', None) or 0
    if point <= 0:
        return 0.0

    # Основной путь: order_calc_profit
    tick = mt5.symbol_info_tick(symbol)
    if tick is not None:
        ask = tick.ask
        sl_price = ask - sl_points * point
        profit = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, 1.0, ask, sl_price)
        if profit is not None:
            return abs(profit)

    # Фоллбэк: старый метод
    tick_size = getattr(info, 'trade_tick_size', None) or getattr(info, 'tick_size', None)
    tick_value = getattr(info, 'trade_tick_value', None) or getattr(info, 'tick_value', None)
    if tick_size and tick_value:
        return sl_points * point * tick_value / tick_size

    return 0.0


def _calc_position_pnl(symbol, lot, entry_price, exit_price, direction, info=None):
    """P&L позиции через order_calc_profit.

    Args:
        symbol: Символ
        lot: Объём
        entry_price: Цена входа
        exit_price: Цена выхода
        direction: 'long' или 'short'
        info: symbol_info (опционально, для фолбэка)

    Returns:
        float — профит/убыток в валюте счёта
    """
    order_type = mt5.ORDER_TYPE_BUY if direction == 'long' else mt5.ORDER_TYPE_SELL
    profit = mt5.order_calc_profit(order_type, symbol, lot, entry_price, exit_price)
    if profit is not None:
        return profit

    # Фоллбэк: старый метод
    if info is None:
        info = mt5.symbol_info(symbol)
    if info is None:
        return 0.0
    tick_size = getattr(info, 'trade_tick_size', None) or getattr(info, 'tick_size', None)
    tick_value = getattr(info, 'trade_tick_value', None) or getattr(info, 'tick_value', None)
    if not tick_size or not tick_value:
        return 0.0
    diff = (exit_price - entry_price) if direction == 'long' else (entry_price - exit_price)
    return (diff / tick_size) * tick_value * lot


# ═══ МЕТРИКИ И СКОРИНГ ═══

def calc_metrics(trade_profits):
    """Считает метрики по списку профитов сделок."""
    if not trade_profits or len(trade_profits) == 0:
        return {
            'profit': 0, 'n_trades': 0, 'profit_factor': 0,
            'max_drawdown': 0, 'win_rate': 0, 'sharpe': 0,
            'avg_trade': 0, 'recovery': 0
        }

    profits = np.array(trade_profits)
    total_profit = profits.sum()
    n = len(profits)

    gross_profit = profits[profits > 0].sum()
    gross_loss = abs(profits[profits < 0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0

    equity = np.cumsum(profits)
    running_max = np.maximum.accumulate(equity)
    drawdowns = running_max - equity
    max_drawdown = drawdowns.max() if len(drawdowns) > 0 else 0

    win_rate = (profits > 0).sum() / n * 100

    if profits.std() > 0:
        sharpe = profits.mean() / profits.std()
    else:
        sharpe = 0

    avg_trade = total_profit / n
    recovery = total_profit / max_drawdown if max_drawdown > 0 else 999.0

    return {
        'profit': total_profit,
        'n_trades': n,
        'profit_factor': profit_factor,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'sharpe': sharpe,
        'avg_trade': avg_trade,
        'recovery': recovery
    }


def composite_score(metrics, weights=None, profit_scale=DEFAULT_PROFIT_SCALE):
    """Композитный скор на основе взвешенной суммы нормированных метрик."""
    if weights is None:
        weights = SCORE_WEIGHTS

    normalized = {
        'profit': metrics['profit'] / profit_scale,
        'profit_factor': min(metrics['profit_factor'], 5) / 2,
        'win_rate': metrics['win_rate'] / 100,
        'sharpe': max(min(metrics['sharpe'], 3), -3) / 3,
        'recovery': min(metrics['recovery'], 10) / 5
    }

    score = sum(weights[k] * normalized[k] for k in weights)
    return score


# ═══ РАСПРЕДЕЛЕНИЕ ЛОТОВ ═══

def distribute_lots(ranked_results, symbol_data, balance,
                    max_risk_pct=0.05, min_lot=0.01, min_score=0.8):
    """Распределяет лоты пропорционально score в рамках квоты риска.

    Использует _normalize_volume для округления лотов по шагу брокера
    и _sl_money_per_lot для расчёта риска SL через order_calc_profit.
    """
    quota = balance * max_risk_pct

    candidates = []
    for r in ranked_results:
        if r['score'] < min_score or r['score'] <= 0:
            continue
        info = symbol_data.get(r['symbol'], {}).get('info')
        if info is None:
            _warn_missing_info(r['symbol'], 'distribute_lots')
            continue
        sl_money = _sl_money_per_lot(r['symbol'], info, r['sl_points'])
        if sl_money <= 0:
            continue
        candidates.append({**r, 'sl_money': sl_money})

    if not candidates:
        return []

    # Сортировка по score — лучшие первыми
    candidates.sort(key=lambda x: x['score'], reverse=True)

    # Жадный отбор: добавляем, пока каждой хватает min_lot
    active = []
    for c in candidates:
        trial = active + [c]
        denom = sum(x['sl_money'] * x['score'] for x in trial)
        raw_lot = quota * c['score'] / denom
        info = symbol_data.get(c['symbol'], {}).get('info')
        if info is not None:
            vol = _normalize_volume(raw_lot, info)
            lot = max(vol, min_lot) if vol is not None else min_lot
        else:
            lot = max(math.floor(raw_lot * 100) / 100, min_lot)
        if lot < min_lot:
            break
        active.append(c)

    if not active:
        return []

    # Лоты пропорционально score, округляем через _normalize_volume
    denom = sum(x['sl_money'] * x['score'] for x in active)
    for x in active:
        info = symbol_data.get(x['symbol'], {}).get('info')
        raw = quota * x['score'] / denom
        if info is not None:
            vol = _normalize_volume(raw, info)
            x['lot'] = max(vol, min_lot) if vol is not None else min_lot
        else:
            x['lot'] = max(math.floor(raw * 100) / 100, min_lot)

    # Масштабируем итеративно, пока суммарный риск ≤ квоты
    for _ in range(20):
        total_risk = sum(x['lot'] * x['sl_money'] for x in active)
        if total_risk <= quota:
            break
        scale = quota / total_risk
        any_floor = False
        for x in active:
            info = symbol_data.get(x['symbol'], {}).get('info')
            scaled_raw = x['lot'] * scale
            if info is not None:
                vol = _normalize_volume(scaled_raw, info)
                scaled = max(vol, min_lot) if vol is not None else min_lot
            else:
                scaled = max(math.floor(scaled_raw * 100) / 100, min_lot)
            if scaled <= min_lot:
                any_floor = True
            x['lot'] = scaled
        if not any_floor:
            break

    return active



# ═══ УТИЛИТЫ ПОЗИЦИЙ ═══

def get_positions(symbol=None, magic=None):
    """Получить все позиции MT5 с фильтрацией."""
    if symbol is not None:
        positions = mt5.positions_get(symbol=symbol)
    else:
        positions = mt5.positions_get()

    if positions is None:
        return []

    result = list(positions)
    if magic is not None:
        result = [p for p in result if p.magic == magic]
    return result


def positions_total(symbol=None, magic=None):
    """Подсчитать количество позиций MT5."""
    return len(get_positions(symbol=symbol, magic=magic))


def get_position_by_ticket(ticket):
    """Получить позицию по тикету."""
    positions = mt5.positions_get(ticket=ticket)
    return positions[0] if positions else None


def get_symbol_positions(symbol):
    """Получить все позиции по символу, сгруппированные по direction."""
    positions = get_positions(symbol=symbol)
    result = {'long': [], 'short': []}
    for p in positions:
        if p.type == mt5.ORDER_TYPE_BUY:
            result['long'].append(p)
        elif p.type == mt5.ORDER_TYPE_SELL:
            result['short'].append(p)
    return result


def check_margin_available(lot, symbol, price, sl_points=0):
    """Проверить, достаточно ли free margin для открытия позиции.

    Args:
        lot: Объём
        symbol: Символ
        price: Цена входа
        sl_points: SL в пунктах (не используется для маржи, оставлен для совместимости)

    Returns:
        tuple: (достаточно: bool, margin_required: float, margin_free: float)
    """
    account = mt5.account_info()
    if account is None:
        return False, 0.0, 0.0

    free_margin = account.margin_free

    # Маржа через MT5 API
    margin_required = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, symbol, lot, price)
    if margin_required is None:
        # Грубый фолбээк
        margin_required = lot * price

    # Буфер 20%
    margin_required *= 1.2

    return free_margin >= margin_required, margin_required, free_margin


def get_stops_levels(symbol):
    """Получить уровни stops/freeze и режим маржи для символа."""
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return {'stops_level': 0, 'freeze_level': 0, 'mode': 'unknown'}

    stops_level = getattr(symbol_info, 'trade_stops_level', 0) or 0
    freeze_level = getattr(symbol_info, 'trade_freeze_level', 0) or 0

    account = mt5.account_info()
    if account is not None:
        margin_mode = account.margin_mode
        # margin_mode: 0=netting, 1=hedging (в Python API — числа)
        mode = 'hedging' if margin_mode == 1 else 'netting'
    else:
        mode = 'unknown'

    return {
        'stops_level': stops_level,
        'freeze_level': freeze_level,
        'mode': mode
    }



def validate_stops(sl_price, tp_price, entry_price, symbol):
    """Проверить, что SL/TP допустимы брокером.

    Returns:
        tuple: (valid: bool, reason: str, min_distance_points: int)
    """
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return False, 'symbol_info not found', 0

    point = getattr(symbol_info, 'point', None) or 0
    stops_level = getattr(symbol_info, 'trade_stops_level', 0) or 0
    min_distance_points = stops_level

    # BUY
    if sl_price < entry_price:
        sl_distance = (entry_price - sl_price) / point
        if sl_distance < min_distance_points:
            return False, f'SL слишком близко: {sl_distance:.0f} < {min_distance_points}', min_distance_points

    if tp_price > entry_price:
        tp_distance = (tp_price - entry_price) / point
        if tp_distance < min_distance_points:
            return False, f'TP слишком близко: {tp_distance:.0f} < {min_distance_points}', min_distance_points

    # SELL
    if sl_price > entry_price:
        sl_distance = (sl_price - entry_price) / point
        if sl_distance < min_distance_points:
            return False, f'SL слишком близко: {sl_distance:.0f} < {min_distance_points}', min_distance_points

    if tp_price < entry_price:
        tp_distance = (entry_price - tp_price) / point
        if tp_distance < min_distance_points:
            return False, f'TP слишком близко: {tp_distance:.0f} < {min_distance_points}', min_distance_points

    return True, 'OK', min_distance_points


def check_position_limits(current_positions, max_total_positions, max_per_symbol):
    """Проверить лимиты на количество позиций.

    Args:
        current_positions: dict {symbol: count}
        max_total_positions: Максимальное общее число позиций
        max_per_symbol: Максимум позиций на один символ

    Returns:
        tuple: (allowed: bool, reason: str, details: dict)
    """
    total = sum(current_positions.values())

    if total >= max_total_positions:
        return False, f'Достигнут лимит общих позиций: {total}/{max_total_positions}', {
            'total': total, 'max': max_total_positions
        }

    for sym, count in current_positions.items():
        if count >= max_per_symbol:
            return False, f'Достигнут лимит для {sym}: {count}/{max_per_symbol}', {
                'symbol': sym, 'count': count, 'max': max_per_symbol
            }

    return True, 'OK', {'total': total, 'max': max_total_positions, 'positions': dict(current_positions)}


def check_daily_loss_limit(initial_balance, current_equity, daily_loss_pct=3.0):
    """Проверить daily stop-loss по убытку.

    Returns:
        tuple: (allowed: bool, daily_loss_pct: float, reason: str)
    """
    account = mt5.account_info()
    if account is None:
        return False, 0.0, 'account_info not available'

    balance = account.balance
    equity = current_equity if current_equity is not None else account.equity

    if initial_balance is None:
        initial_balance = balance

    if initial_balance <= 0:
        return True, 0.0, 'initial_balance invalid (<=0)'

    daily_loss = ((initial_balance - equity) / initial_balance) * 100

    if daily_loss >= daily_loss_pct:
        return False, daily_loss, f'Daily loss {daily_loss:.2f}% >= {daily_loss_pct}%'

    return True, daily_loss, f'OK: daily loss {daily_loss:.2f}% < {daily_loss_pct}%'


def check_equity_stop(current_equity, initial_equity, equity_stop_pct=10.0):
    """Проверить equity stop — глобальный стоп при просадке.

    Returns:
        tuple: (allowed: bool, drawdown_pct: float, reason: str)
    """
    if initial_equity <= 0:
        return True, 0.0, 'initial_equity invalid'

    drawdown = ((initial_equity - current_equity) / initial_equity) * 100

    if drawdown >= equity_stop_pct:
        return False, drawdown, f'Equity drawdown {drawdown:.2f}% >= {equity_stop_pct}%'

    return True, drawdown, f'OK: drawdown {drawdown:.2f}% < {equity_stop_pct}%'


def realtime_quota_recalc(balance, current_positions, max_risk_pct=0.05):
    """Пересчёт квоты в реальном времени.

    Args:
        balance: Текущий баланс
        current_positions: Список активных позиций с 'lot', 'sl_points', 'symbol'
        max_risk_pct: Максимальный риск в % от баланса

    Returns:
        tuple: (quota_ok: bool, current_risk_pct: float, quota: float)
    """
    quota = balance * max_risk_pct

    total_risk = 0
    for pos in current_positions:
        info = mt5.symbol_info(pos['symbol'])
        if info is None:
            _warn_missing_info(pos['symbol'], 'realtime_quota_recalc')
            continue
        sl = pos.get('sl_points') or 0
        sl_money = _sl_money_per_lot(pos['symbol'], info, sl) * pos.get('lot', 0)
        total_risk += sl_money

    current_risk_pct = (total_risk / balance * 100) if balance > 0 else 0

    return total_risk <= quota, current_risk_pct, quota


# ═══ УТИЛИТЫ ОБЪЁМА ═══

def _normalize_volume(lot, info):
    """Округляет лот вниз до шага объёма; None — если вне [volume_min, volume_max]."""
    if info is None:
        return lot
    step = getattr(info, 'trade_volume_step', None) or getattr(info, 'volume_step', None)
    if not step or step <= 0:
        step = DEFAULT_LOT
    vmin = getattr(info, 'trade_volume_min', None) or getattr(info, 'volume_min', None) or 0.01
    vmax = getattr(info, 'trade_volume_max', None) or getattr(info, 'volume_max', None) or 1e9
    volume = math.floor(lot / step + 1e-9) * step
    if volume < vmin - 1e-9 or volume > vmax + 1e-9:
        return None
    return round(volume, 8)


def _position_profit(s, exit_price, symbol_data):
    """P&L позиции при закрытии по exit_price (в валюте счёта)."""
    pos = s.get('position')
    if pos is None:
        return 0.0

    symbol = s['symbol']
    lot = pos['lot']
    entry_price = pos['entry_price']
    direction = pos['direction']

    info = symbol_data.get(symbol, {}).get('info')
    return _calc_position_pnl(symbol, lot, entry_price, exit_price, direction, info)
