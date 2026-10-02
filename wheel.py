import numpy as np
from typing import List, Dict, Any


def _ccy_base(symbol: str) -> str:
    """'EURUSDrfd' -> 'EUR'; 'USDJPYrfd' -> 'JPY' — короткое имя для подписей."""
    s = str(symbol)
    if s.lower().endswith('rfd'):
        s = s[:-3]
    if len(s) >= 6 and s.startswith('USD'):
        return s[3:]
    return s[:3] if len(s) >= 3 else s


def category_label(symbol: str, family: str) -> str:
    """Имя категории «символ + семейство»: 'EUR - parabolic'."""
    return f"{_ccy_base(symbol)} - {family}"


def calculate_steering_wheel_quotas(
        strategies_data: List[Dict[str, Any]],
        current_quotas: Dict[str, float],
        alpha: float = 0.2,
        min_q: float = 0.05,
        max_q: float = 0.35,
        min_trades: int = 10,
        max_dd: float = 0.15,
        score_mode: str = 'pnl',
        eps: float = 0.01,
) -> Dict[str, float]:
    """
    Новые квоты ДЛЯ ВСЕХ категорий из current_quotas.
    Категория = «символ + семейство» (id = f"{symbol}_{type}"), например 'EURUSDrfd_rf'.

    score_mode:
      'pnl'    (по умолчанию) — вес получают только ПРИБЫЛЬНЫЕ категории:
               score = max(pnl, 0), нормализация к сумме 1. Убыточные получают
               score=0 и плавно сползают к полу min_q через EMA. Картина совпадает
               с вкладкой Strategies (P&L by Family): кто выигрывает — тот растёт.
               Фильтр max_dd в этом режиме НЕ применяется (просадка в рублях
               не имеет смысла как порог).
      'sharpe' — риск-скорректированный вес: score = pnl / (vol + eps).
               Здесь фильтр max_dd работает (drawdown считается долей от PnL).

    Устойчивость перераспределения:
      * пол min_q автоматически ограничивается средней долей (1/N) — иначе
        при N*min_q > 1 квоты физически не могут суммироваться в 100%;
      * у доноров никогда не отнимается больше, чем у них есть сверх пола —
        квоты не уходят в отрицательные значения;
      * итоговая сумма всегда равна 1.0 (с точностью округления).
    """
    # 1. Фильтр только для расчёта СКОРА (для скоринга берем только надежные).
    #    max_dd применяется ТОЛЬКО в режиме 'sharpe': в 'pnl' фильтр по просадке
    #    в рублях бессмысленен — любая серия убытков дороже max_dd (0.15 руб.)
    #    выбивает категорию, score_map пустеет, и все квоты сползаются к равным
    #    долям: лидеры теряют, аутсайдеры растут (ровно обратный желаемому).
    valid_strategies = []
    for s in strategies_data:
        if s.get("trades", 0) < min_trades:
            continue
        if s.get("pnl") is None or s.get("vol") is None:
            continue
        if score_mode == 'sharpe' and s.get("drawdown", 1.0) > max_dd:
            continue
        valid_strategies.append(s)

    # 2. Скоринг категорий: id -> нормализованный вес (только для валидных)
    score_map = {}
    if valid_strategies:
        scores = []
        for s in valid_strategies:
            if score_mode == 'sharpe':
                # Риск-скорректированный вес; для 1-2 сделок (vol=0) — просто pnl
                if s["vol"] > 0:
                    score = s["pnl"] / (s["vol"] + eps)
                else:
                    score = np.clip(s["pnl"], -1000, 10000)
            else:
                # 'pnl': вес только у прибыльных (как P&L by Family на Strategies)
                score = max(float(s["pnl"]), 0.0)
            scores.append((s["id"], score))

        total_score = sum(score for _, score in scores)
        if total_score > 0:
            # Убыточные попадают в score_map со значением 0.0 — их цель = 0,
            # они НЕ получают base_share и плавно уходят вниз к полу.
            score_map = {sid: score / total_score for sid, score in scores}

    # 3. Расчет новых квот для ВСЕХ категорий (включая невалидные).
    #    Если текущих квот нет — выходим (нечего обновлять).
    if not current_quotas:
        return {}

    n = len(current_quotas)
    base_share = 1.0 / max(n, 1)

    new_quotas = {}
    for sid, prev_q in current_quotas.items():
        # Получаем целевой вес из скоринга, если категория валидна
        target_weight = score_map.get(sid, base_share)
        # Плавное обновление (EMA); квота не ниже нуля
        new_q = alpha * target_weight + (1.0 - alpha) * max(prev_q, 0.0)
        new_q = max(new_q, 0.0)
        new_quotas[sid] = new_q

    # 4. Применение ограничений min_q / max_q.
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

    # 5. Докрутка: поднимаем выпавших ниже пола, забирая у остальных строго
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

    # 6. Финальная нормализация (гарантия суммы = 1.0)
    total = sum(result.values())
    if total > 0:
        result = {k: v / total for k, v in result.items()}
    return result


def build_metrics_from_journal(journal_df, n_last=10, family_map=None):
    """Метрики по КАТЕГОРИЯМ «символ + семейство» (type из реестра).

    Приоритет определения семейства:
      1) колонка strategy_type в df (есть в trades_df из daily_report);
      2) family_map: ключ f"{symbol}_{param_key}" -> type (для журнала main.py);
      3) фоллбэк: семейством считается param_key (максимальная совместимость).

    Каждая метрика: id = f"{symbol}_{family}", label = 'EUR - rf',
    family, symbol, pnl, vol, trades, drawdown.
    drawdown — максимальная просадка серии как ДОЛЯ от модуля PnL
    (0.15 = 15%), чтобы порог max_dd имел смысл в режиме 'sharpe'.
    """
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

    # Семейство (type): 1) готовая колонка, 2) реестр, 3) фоллбэк на param_key
    if 'strategy_type' in df.columns:
        fam_col = 'strategy_type'
    elif family_map:
        df['strategy_type'] = df.apply(
            lambda r: family_map.get(f"{r['symbol']}_{r['param_key']}", 'unknown'),
            axis=1)
        fam_col = 'strategy_type'
    else:
        df['strategy_type'] = df['param_key'].astype(str)
        fam_col = 'strategy_type'

    if 'exit_time' in df.columns:
        df = df.sort_values('exit_time')
    else:
        # Если нет времени выхода, сортируем по индексу (предполагаем хронологию)
        df = df.sort_index()

    metrics = []
    for (symbol, fam), grp in df.groupby(['symbol', fam_col]):
        grp = grp.tail(n_last)
        profits = grp['profit'].astype(float)
        trades = int(len(profits))

        if trades == 0:
            continue

        pnl = float(profits.sum())
        # Защита от std на 1 сделке
        vol = float(profits.std(ddof=0)) if trades > 1 else 0.0

        # Просадка как ДОЛЯ от модуля PnL (в рублях порог max_dd не имеет смысла)
        cum = profits.cumsum()
        if cum.empty:
            drawdown = 0.0
        else:
            peak = cum.cummax()
            dd_abs = float((peak - cum).max())
            if dd_abs < 0:
                dd_abs = 0.0
            drawdown = dd_abs / max(1.0, abs(pnl))

        metrics.append({
            'id': f"{symbol}_{fam}",
            'label': category_label(symbol, fam),
            'family': fam,
            'symbol': symbol,
            'pnl': pnl,
            'vol': vol,
            'trades': trades,
            'drawdown': drawdown,
        })
    return metrics