"""Управление рисками: метрики, скоринг, распределение лотов."""
import math
import numpy as np


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
