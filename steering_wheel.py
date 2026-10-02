import math
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
            # Считаем скор даже для убыточных, чтобы они не исчезали, а получали min_q
            score = s["pnl"] / (s["vol"] + eps)
            scores.append((s["id"], score))

        total_score = sum(score for _, score in scores)
        if total_score != 0:
            score_map = {sid: score / total_score for sid, score in scores}

    # 2. Расчет новых квот для ВСЕХ стратегий (включая невалидные)
    new_quotas = {}

    # Если вообще нет данных, возвращаем текущие без изменений
    if not score_map and not current_quotas:
        return {}

    # Базовое распределение: если есть скор - берем его, если нет - даем равномерную долю
    base_share = 1.0 / max(len(current_quotas), 1)

    for sid, prev_q in current_quotas.items():
        # Получаем целевой вес из скоринга, если стратегия валидна
        target_weight = score_map.get(sid, base_share)

        # Плавное обновление (EMA)
        new_q = alpha * target_weight + (1.0 - alpha) * prev_q

        # Сохраняем в словарь
        new_quotas[sid] = new_q

    # 3. Применение ограничений min_q / max_q с перераспределением излишка
    # Сначала обрезаем сверху
    excess = 0.0
    for sid in new_quotas:
        if new_quotas[sid] > max_q:
            excess += new_quotas[sid] - max_q
            new_quotas[sid] = max_q

    # Распределяем излишек среди тех, кто ниже max_q, пропорционально их текущей доле
    # (или просто равномерно, если хочешь упростить)
    active_ids = [sid for sid in new_quotas if new_quotas[sid] < max_q]
    if active_ids and excess > 0:
        total_active = sum(new_quotas[sid] for sid in active_ids)
        if total_active > 0:
            for sid in active_ids:
                new_quotas[sid] += excess * (new_quotas[sid] / total_active)

    # Теперь применяем min_q. Если доля меньше min_q, поднимаем до min_q
    # и забираем эту разницу у остальных пропорционально
    deficits = 0.0
    for sid in new_quotas:
        if new_quotas[sid] < min_q:
            deficits += min_q - new_quotas[sid]
            new_quotas[sid] = min_q

    if deficits > 0:
        # Забираем у тех, кто выше min_q
        donors = [sid for sid in new_quotas if new_quotas[sid] > min_q]
        if donors:
            total_donor = sum(new_quotas[sid] - min_q for sid in donors)
            if total_donor > 0:
                for sid in donors:
                    share = (new_quotas[sid] - min_q) / total_donor
                    new_quotas[sid] -= deficits * share

    # Финальная нормализация (на случай ошибок округления)
    total = sum(new_quotas.values())
    if total > 0:
        new_quotas = {k: v / total for k, v in new_quotas.items()}

    return new_quotas


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
