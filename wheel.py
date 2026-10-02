import math
import numpy as np
from typing import List, Dict, Any


def calculate_steering_wheel_quotas(
        strategies_data: List[Dict[str, Any]],
        current_quotas: Dict[str, float],
        alpha: float = 0.2,
        min_q: float = 0.05,
        max_q: float = 0.35,
        min_trades: int = 10,
        max_dd: float = 0.15,
        eps: float = 0.01
) -> Dict[str, float]:
    """
    Возвращает новые квоты ДЛЯ ВСЕХ стратегий из current_quotas.
    Стратегии без достаточной статистики получают min_q или сохраняют текущую долю.

    Устойчивость перераспределения:
      * пол min_q автоматически ограничивается средней долей (1/N) — иначе
        при N*min_q > 1 квоты физически не могут суммироваться в 100%;
      * у доноров никогда не отнимается больше, чем у них есть сверх пола —
        квоты не уходят в отрицательные значения;
      * итоговая сумма всегда равна 1.0 (с точностью округления).
    """
    # 1. Фильтрация только для расчета СКОРА (для скоринга берем только надежные)
    valid_strategies = [
        s for s in strategies_data
        if s.get("trades", 0) >= min_trades
           and s.get("drawdown", 1.0) <= max_dd
           and s.get("pnl") is not None
           and s.get("vol") is not None
    ]

    # Словарь скоринга: id -> нормализованный вес (только для валидных)
    score_map = {}
    if valid_strategies:
        scores = []
        for s in valid_strategies:
            # Для стратегий с 1 сделкой используем только pnl (vol=0)
            # Для >=2 сделок: score = pnl / vol (risk-adjusted return)
            if s["vol"] > 0:
                score = s["pnl"] / (s["vol"] + eps)
            else:
                # Одна сделка — без волатильности, просто pnl с ограничением
                score = np.clip(s["pnl"], -1000, 10000)
            scores.append((s["id"], score))

        total_score = sum(score for _, score in scores)
        if total_score != 0:
            score_map = {sid: score / total_score for sid, score in scores}

    # 2. Расчет новых квот для ВСЕХ стратегий (включая невалидные).
    #    Если текущих квот нет — выходим (нечего обновлять).
    if not current_quotas:
        return {}

    n = len(current_quotas)
    base_share = 1.0 / max(n, 1)

    new_quotas = {}
    for sid, prev_q in current_quotas.items():
        # Получаем целевой вес из скоринга, если стратегия валидна
        target_weight = score_map.get(sid, base_share)
        # Плавное обновление (EMA); квота не ниже нуля
        new_q = alpha * target_weight + (1.0 - alpha) * max(prev_q, 0.0)
        new_q = max(new_q, 0.0)
        new_quotas[sid] = new_q

    # 3. Применение ограничений min_q / max_q.
    # Пол не может превышать среднюю долю (1/N) — иначе полы не влезают в 100%.
    effective_min = min(min_q, base_share)
    effective_max = max(max_q, effective_min)

    # Клип к [effective_min, effective_max]
    clipped = {sid: min(max(q, effective_min), effective_max)
               for sid, q in new_quotas.items()}

    # Нормализация к сумме 1.0
    total = sum(clipped.values())
    if total <= 0:
        # Аварийный фоллбэк: равные доли
        return {sid: base_share for sid in current_quotas}

    result = {sid: q / total for sid, q in clipped.items()}

    # Докрутка: поднимаем выпавших ниже пола, забирая у остальных строго
    # в пределах их излишка над полом (квоты не уходят в минус).
    for _ in range(20):
        below = [sid for sid, q in result.items() if q < effective_min]
        if not below:
            break
        deficit = sum(effective_min - result[sid] for sid in below)
        above = [sid for sid, q in result.items() if q > effective_min]
        avail = sum(result[sid] - effective_min for sid in above)
        if avail <= 0:
            break
        take = min(deficit, avail)
        for sid in below:
            result[sid] = effective_min
        for sid in above:
            share = (result[sid] - effective_min) / avail
            result[sid] -= take * share

    # Финальная нормализация (гарантия суммы = 1.0)
    total = sum(result.values())
    if total > 0:
        result = {k: v / total for k, v in result.items()}
    return result


def build_metrics_from_journal(journal_df, n_last=10):
    if journal_df is None or journal_df.empty:
        return []

    df = journal_df.copy()
    df = df.reset_index(drop=True)
    df = df.loc[:, ~df.columns.duplicated()]

    required_cols = ['symbol', 'param_key', 'profit']
    if not all(col in df.columns for col in required_cols):
        return []

    df = df[df['profit'].notna()]
    if df.empty:
        return []

    if 'exit_time' in df.columns:
        df = df.sort_values('exit_time')
    else:
        # Если нет времени выхода, сортируем по индексу (предполагаем хронологию)
        df = df.sort_index()

    metrics = []
    for (symbol, param_key), grp in df.groupby(['symbol', 'param_key']):
        grp = grp.tail(n_last)
        profits = grp['profit'].astype(float)
        trades = int(len(profits))

        if trades == 0:
            continue

        pnl = float(profits.sum())
        # Защита от std на 1 сделке
        vol = float(profits.std(ddof=0)) if trades > 1 else 0.0

        # Просадка
        cum = profits.cumsum()
        if cum.empty:
            drawdown = 0.0
        else:
            peak = cum.cummax()
            drawdown = float((peak - cum).max())
            if drawdown < 0: drawdown = 0.0

        metrics.append({
            'id': f"{symbol}_{param_key}",
            'pnl': pnl,
            'vol': vol,
            'trades': trades,
            'drawdown': drawdown,
        })
    return metrics
