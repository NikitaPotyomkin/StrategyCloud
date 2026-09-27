"""Управление рисками: метрики, скоринг, распределение лотов."""
import math
import numpy as np
import MetaTrader5 as mt5
import datetime


# ═══ КОНСТАНТЫ ОЦЕНКИ ═══
# Веса composite_score (см. функцию ниже).
SCORE_WEIGHTS = {
    'profit': 0.35,
    'profit_factor': 0.25,
    'win_rate': 0.15,
    'sharpe': 0.15,
    'recovery': 0.10,
}
# Делитель profit при нормировке. Для рублёвых счетов с крупными профитами
# значение по умолчанию может быть мало: profit начнёт доминировать в скоре.
# Подбирай по медиане profit за окно бэктеста (см. composite_score).
DEFAULT_PROFIT_SCALE = 1000.0

# Лот по умолчанию, если в записи стратегии нет 'lot'.
DEFAULT_LOT = 0.01


# ═══ МЕТРИКИ И СКОРИНГ ═══

def calc_metrics(trade_profits):
    """
    Считает метрики по списку профитов сделок.
    Возвращает dict с метриками.
    """
    if not trade_profits or len(trade_profits) == 0:
        return {
            'profit': 0, 'n_trades': 0, 'profit_factor': 0,
            'max_drawdown': 0, 'win_rate': 0, 'sharpe': 0,
            'avg_trade': 0, 'recovery': 0
        }

    profits = np.array(trade_profits)
    total_profit = profits.sum()
    n = len(profits)

    # Profit Factor
    gross_profit = profits[profits > 0].sum()
    gross_loss = abs(profits[profits < 0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0

    # Max Drawdown (по кривой equity)
    equity = np.cumsum(profits)
    running_max = np.maximum.accumulate(equity)
    drawdowns = running_max - equity
    max_drawdown = drawdowns.max() if len(drawdowns) > 0 else 0

    # Win Rate
    win_rate = (profits > 0).sum() / n * 100

    # Sharpe (упрощённый, без risk-free rate)
    if profits.std() > 0:
        sharpe = profits.mean() / profits.std()
    else:
        sharpe = 0

    # Avg Trade
    avg_trade = total_profit / n

    # Recovery Factor
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
    """
    Композитный скор на основе взвешенной суммы нормированных метрик.

    Веса по умолчанию:
      profit       — 0.35  (главный драйвер)
      profit_factor— 0.25  (качество прибыли)
      win_rate     — 0.15  (стабильность)
      sharpe       — 0.15  (ровность кривой)
      recovery     — 0.10  (восстановление после просадки)

    Нормировка — константами: profit/1000, PF/2, WinRate/100, Sharpe/3, Recov/5.
    ВНИМАНИЕ: константы эмпирические. При крупных профитах (рублёвый счёт)
    profit доминирует независимо от весов — нормируй profit по медиане
    результатов окна бэктеста, а не по 1000.
    """
    if weights is None:
        weights = SCORE_WEIGHTS

    # Нормировка: приводим к сопоставимому масштабу
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
    """Распределяет лоты пропорционально score в рамках квоты риска."""
    quota = balance * max_risk_pct

    candidates = []
    for r in ranked_results:
        if r['score'] < min_score or r['score'] <= 0:
            continue
        info = symbol_data.get(r['symbol'], {}).get('info')
        if info is None:
            continue
        sl_money = (r['sl_points'] * info.point
                    * info.trade_tick_value / info.trade_tick_size)
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
        lot = quota * c['score'] / denom
        if lot < min_lot:
            break
        active.append(c)

    if not active:
        return []

    # Лоты пропорционально score, округляем до шага (0.01)
    denom = sum(x['sl_money'] * x['score'] for x in active)
    for x in active:
        raw = quota * x['score'] / denom
        x['lot'] = max(math.floor(raw * 100) / 100, min_lot)

    # Проверка: не превысили ли квоту (min_lot может дать перекос) —
    # масштабируем итеративно, пока суммарный риск ≤ квоты.
    for _ in range(20):
        total_risk = sum(x['lot'] * x['sl_money'] for x in active)
        if total_risk <= quota:
            break
        scale = quota / total_risk
        any_floor = False
        for x in active:
            scaled = math.floor(x['lot'] * scale * 100) / 100
            if scaled < min_lot:
                scaled = min_lot
                any_floor = True
            x['lot'] = scaled
        if not any_floor:
            break

    return active


# ═══ УТИЛИТЫ ПОЗИЦИЙ ═══

def get_positions(symbol=None, magic=None):
    """Получить все позиции MT5 с фильтрацией по символу и magic.
    
    Возвращает список объектов mt5.PositionInfo.
    """
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
    """Подсчитать количество позиций MT5.
    
    Args:
        symbol: Символ или None для всех символов
        magic: Magic number или None для всех маджиков
    
    Returns:
        int — количество позиций
    """
    return len(get_positions(symbol=symbol, magic=magic))


def get_position_by_ticket(ticket):
    """Получить позицию по тикету.
    
    Returns:
        mt5.PositionInfo или None
    """
    positions = mt5.positions_get(ticket=ticket)
    return positions[0] if positions else None


def get_symbol_positions(symbol):
    """Получить все позиции по символу, сгруппированные по direction.
    
    Returns:
        dict: {'long': [...], 'short': [...]}
    """
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
        lot: Объём позиции
        symbol: Символ
        price: Цена входа
        sl_points: SL в пунктах (опционально)
    
    Returns:
        tuple: (достаточно: bool, margin_required: float, margin_free: float)
    """
    account = mt5.account_info()
    if account is None:
        return False, 0.0, 0.0
    
    free_margin = account.margin_free
    
    # Рассчитать требуемую маржу
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return False, 0.0, free_margin
    
    # Маржа = объём × цена × размер контракта
    margin_required = lot * price * symbol_info.trade_tick_value / symbol_info.trade_tick_size
    
    # Добавить буфер на SL (если указан)
    if sl_points > 0:
        point = symbol_info.point
        sl_money = sl_points * point * lot * symbol_info.trade_tick_value / symbol_info.trade_tick_size
        margin_required += sl_money
    
    # Проверить с запасом 20%
    margin_required *= 1.2
    
    return free_margin >= margin_required, margin_required, free_margin


def get_stops_levels(symbol):
    """Получить уровни stops/freeze для символа.
    
    Returns:
        dict: {'stops_level': int, 'freeze_level': int, 'mode': str}
    """
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return {'stops_level': 0, 'freeze_level': 0, 'mode': 'unknown'}
    
    return {
        'stops_level': symbol_info.stops_level,
        'freeze_level': symbol_info.freeze_level,
        'mode': 'hedging' if getattr(symbol_info, 'exchange', False) else 'netting'
    }


def validate_stops(sl_price, tp_price, entry_price, symbol):
    """Проверить, что SL/TP допустимы брокером.
    
    Args:
        sl_price: Цена SL
        tp_price: Цена TP
        entry_price: Цена входа
        symbol: Символ
    
    Returns:
        tuple: (valid: bool, reason: str, min_distance_points: int)
    """
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return False, 'symbol_info not found', 0
    
    point = symbol_info.point
    stops_level = symbol_info.stops_level
    
    # Минимальное расстояние в пунктах
    min_distance_points = stops_level // point if point > 0 else 10
    
    # Проверка для BUY позиции
    if sl_price < entry_price:  # BUY SL ниже
        sl_distance = (entry_price - sl_price) / point
        if sl_distance < min_distance_points:
            return False, f'SL слишком близко: {sl_distance:.0f} < {min_distance_points}', min_distance_points
    
    if tp_price > entry_price:  # BUY TP выше
        tp_distance = (tp_price - entry_price) / point
        if tp_distance < min_distance_points:
            return False, f'TP слишком близко: {tp_distance:.0f} < {min_distance_points}', min_distance_points
    
    # Проверка для SELL позиции
    if sl_price > entry_price:  # SELL SL выше
        sl_distance = (sl_price - entry_price) / point
        if sl_distance < min_distance_points:
            return False, f'SL слишком близко: {sl_distance:.0f} < {min_distance_points}', min_distance_points
    
    if tp_price < entry_price:  # SELL TP ниже
        tp_distance = (entry_price - tp_price) / point
        if tp_distance < min_distance_points:
            return False, f'TP слишком близко: {tp_distance:.0f} < {min_distance_points}', min_distance_points
    
    return True, 'OK', min_distance_points


def check_position_limits(current_positions, max_total_positions, max_per_symbol):
    """Проверить лимиты на количество позиций.
    
    Args:
        current_positions: dict {symbol: count} — текущие позиции по символам
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
    
    Args:
        initial_balance: Баланс на начало дня
        current_equity: Текущая equity
        daily_loss_pct: Максимальный убыток в % от баланса
    
    Returns:
        tuple: (allowed: bool, daily_loss_pct: float, reason: str)
    """
    account = mt5.account_info()
    if account is None:
        return False, 0.0, 'account_info not available'
    
    balance = account.balance
    equity = account.equity
    
    # Если initial_balance не передан, используем balance
    if initial_balance is None:
        initial_balance = balance
    
    daily_loss = ((initial_balance - equity) / initial_balance) * 100
    
    if daily_loss >= daily_loss_pct:
        return False, daily_loss, f'Daily loss {daily_loss:.2f}% >= {daily_loss_pct}%'
    
    return True, daily_loss, f'OK: daily loss {daily_loss:.2f}% < {daily_loss_pct}%'


def check_equity_stop(current_equity, initial_equity, equity_stop_pct=10.0):
    """Проверить equity stop — глобальный стоп при просадке.
    
    Args:
        current_equity: Текущая equity
        initial_equity: Начальная equity (старт бота)
        equity_stop_pct: Максимальная просадка в %
    
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
    
    Проверяет, не превышена ли квота риска при изменении баланса.
    
    Args:
        balance: Текущий баланс
        current_positions: Список активных позиций с полями 'lot', 'sl_points', 'symbol'
        max_risk_pct: Максимальный риск в % от баланса
    
    Returns:
        tuple: (quota_ok: bool, current_risk: float, quota: float)
    """
    quota = balance * max_risk_pct
    
    # Рассчитать текущий риск
    total_risk = 0
    for pos in current_positions:
        info = mt5.symbol_info(pos['symbol'])
        if info is None:
            continue
        sl_money = pos['sl_points'] * info.point * pos['lot'] * info.trade_tick_value / info.trade_tick_size
        total_risk += sl_money
    
    current_risk_pct = (total_risk / balance * 100) if balance > 0 else 0
    
    return total_risk <= quota, current_risk_pct, quota


# ═══ УТИЛИТЫ ПОЗИЦИЙ ═══

def _normalize_volume(lot, info):
    """Округляет лот вниз до шага объёма; None — если вне [volume_min, volume_max]."""
    if info is None:
        return lot
    step = info.volume_step if info.volume_step > 0 else DEFAULT_LOT
    volume = math.floor(lot / step + 1e-9) * step
    if volume < info.volume_min - 1e-9 or volume > info.volume_max + 1e-9:
        return None
    return round(volume, 8)


def _position_profit(s, exit_price, symbol_data):
    """P&L позиции s при закрытии по exit_price (в валюте счёта)."""
    info = symbol_data[s['symbol']]['info']
    diff = (exit_price - s['position']['entry_price']) if s['position']['direction'] == 'long' \
        else (s['position']['entry_price'] - exit_price)
    return (diff / info.trade_tick_size) * info.trade_tick_value * s['position']['lot']
