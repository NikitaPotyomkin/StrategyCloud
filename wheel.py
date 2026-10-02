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

def calculate_steering_wheel_quotas(strategies_data, current_quotas, steering_cfg):
    """
    Расчёт квот с усилением лидеров (Power Law).
    Стратегии без сделок сохраняют текущую долю (консервативный режим).
    Финальная нормализация гарантирует сумму = 1.0.
    """
    gamma = steering_cfg.get('gamma', 1.5)
    min_q = steering_cfg.get('min_q', 0.01)
    max_q = steering_cfg.get('max_q', 0.5)
    alpha = steering_cfg.get('alpha', 0.3)
    score_mode = steering_cfg.get('score_mode', 'pnl')

    # ── 1. Сырые баллы с усилением Power Law ──
    scores = []
    for s in strategies_data:
        if not isinstance(s, dict):
            continue

        sid = s.get("id")
        if sid is None:
            continue

        pnl_raw = s.get("pnl", 0) or 0.0

        if score_mode == 'sharpe':
            vol = s.get("vol", 0) or 0.0
            if vol <= 0:
                score = pnl_raw * 10.0
            else:
                score = pnl_raw / vol
        else:
            score = max(float(pnl_raw), 0.0)

        if score > 0:
            score = score ** gamma

        scores.append((sid, score))

    total_score = sum(sc for _, sc in scores)

    # Все в минусе или нет данных — возвращаем текущие квоты как есть
    if total_score <= 0 or not scores:
        return current_quotas

    target_weights = {sid: sc / total_score for sid, sc in scores}

    # ── 2. EMA + Floor/Ceiling для стратегий со сделками ──
    new_quotas = {}
    for sid, target in target_weights.items():
        current = current_quotas.get(sid, 0.0)
        raw_new = alpha * target + (1.0 - alpha) * current
        new_quotas[sid] = max(min_q, min(max_q, raw_new))

    # ── 3. Стратегии БЕЗ сделок — сохраняем текущую долю ──
    # (консервативный режим: не обнуляем, а оставляем как было)
    scored_ids = set(target_weights.keys())
    base_share = 1.0 / len(current_quotas) if current_quotas else 0.0
    for sid in current_quotas:
        if sid not in scored_ids:
            new_quotas[sid] = current_quotas[sid]

    # ── 4. Финальная нормализация к 1.0 ──
    total = sum(new_quotas.values())
    if total > 0:
        new_quotas = {k: v / total for k, v in new_quotas.items()}
    else:
        n = len(new_quotas)
        if n > 0:
            new_quotas = {k: 1.0 / n for k in new_quotas}

    return new_quotas



def build_metrics_from_journal(journal_df, n_last=10, family_map=None, min_trades_filter=3):
    """
    min_trades_filter: минимальное кол-во сделок для попадания в штурвал.
    """
    # ИСПРАВЛЕНО: Всегда возвращаем список, даже если данных нет.
    # Если вернуть None, calculate_steering_wheel_quotas упадет с ошибкой.
    if journal_df is None or journal_df.empty:
        return

    df = journal_df.copy()
    df = df.reset_index(drop=True)
    df = df.loc[:, ~df.columns.duplicated()]

    required_cols = ['symbol', 'param_key', 'profit']
    if not all(col in df.columns for col in required_cols):
        return

    df = df[df['profit'].notna()]
    if df.empty:
        return

        # ИСПРАВЛЕНО: Убран лишний отступ у этого блока кода
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
        df = df.sort_index()

    metrics =[]
    for (symbol, fam), grp in df.groupby(['symbol', fam_col]):
        grp = grp.tail(n_last)
        profits = grp['profit'].astype(float)
        trades = int(len(profits))

        # ФИЛЬТР: Игнорируем стратегии с малым количеством сделок
        if trades < min_trades_filter:
            continue

        pnl = float(profits.sum())
        vol = float(profits.std(ddof=0)) if trades > 1 else 0.0

        # Просадка как ДОЛЯ от модуля PnL
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
