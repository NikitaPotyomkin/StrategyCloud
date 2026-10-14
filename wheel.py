import numpy as np
import pandas as pd
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

def compute_categories(trades_df, family_col='strategy_type', symbol_col='symbol',
                       pnl_col='profit_net', volume_col='volume'):
    """ЕДИНЫЙ источник категорий «символ + семейство» из окна сделок.

    Считает PnL по ВСЕМУ переданному окну (никакого n_last) — именно это
    число видно в Strategy Tree на уровне Symbol. Поэтому Tree и Wheel
    не могут разойтись: оба берут категории отсюда.

    Возвращает список dict:
        id, label, family, symbol, pnl, volume, vol (std), trades
    Отсортирован по PnL по убыванию.
    """
    if trades_df is None or len(trades_df) == 0:
        return []

    df = trades_df.copy().reset_index(drop=True)

    # Гибкий выбор колонок (на случай иных имён во входном DataFrame)
    if family_col not in df.columns:
        family_col = 'type' if 'type' in df.columns else None
    if symbol_col not in df.columns:
        return []
    if pnl_col not in df.columns:
        pnl_col = 'profit' if 'profit' in df.columns else None
    if family_col is None or pnl_col is None:
        return []

    df[pnl_col] = pd.to_numeric(df[pnl_col], errors='coerce').fillna(0.0)
    has_vol = volume_col in df.columns
    if has_vol:
        df[volume_col] = pd.to_numeric(df[volume_col], errors='coerce').fillna(0.0)

    metrics = []
    for (symbol, fam), grp in df.groupby([symbol_col, family_col]):
        profits = grp[pnl_col].astype(float)
        pnl = float(profits.sum())
        volume = float(grp[volume_col].sum()) if has_vol else 0.0
        vol = float(profits.std(ddof=0)) if len(profits) > 1 else 0.0
        metrics.append({
            'id': f"{symbol}_{fam}",
            'label': category_label(symbol, fam),
            'family': fam,
            'symbol': symbol,
            'pnl': pnl,
            'volume': volume,
            'vol': vol,
            'trades': int(len(profits)),
        })

    metrics.sort(key=lambda m: m['pnl'], reverse=True)
    return metrics


def format_allocation_report(categories, current_quotas, new_quotas,
                             lookback_days, top_n=15, min_trades=0, score_mode='pnl'):
    """Строки лога «Strategy Tree → квоты» для момента перекладки объёма.

    Ранг = метрика штурвала (по умолчанию абсолютный PnL за окно, как в дереве;
    для 'pnl_per_lot' — удельная прибыль ₽ за лот). Возвращает строки для print().
    """
    if not categories:
        return [f"  [WHEEL] Окно {lookback_days} дн.: категорий нет — квоты не меняются."]

    lines = [f"  [WHEEL] Аллокация за {lookback_days} дн. "
             f"(ранг = {'PnL / объём, ₽ за лот' if score_mode == 'pnl_per_lot' else 'PnL за окно'}):"]
    # Порядок строк = метрика штурвала (иначе ранг в логе не совпадал бы с квотами)
    if score_mode == 'pnl_per_lot':
        _cats = sorted(categories, key=lambda c: (c['pnl'] / c['volume']) if c.get('volume') else 0.0,
                       reverse=True)
    else:
        _cats = list(categories)
    for i, c in enumerate(_cats[:top_n], 1):
        q_new = new_quotas.get(c['id'], 0.0)
        q_cur = current_quotas.get(c['id'], 0.0)
        delta_pp = (q_new - q_cur) * 100.0
        arrow = '↑' if delta_pp > 1e-6 else ('↓' if delta_pp < -1e-6 else '=')
        lines.append(
            f"    {i:>2}. {c['label']:<26} PnL {c['pnl']:>+10,.0f} ₽  "
            f"{(c['pnl'] / c['volume'] if c.get('volume') else 0.0):>+8,.0f} ₽/лот  "
            f"квота {q_cur*100:5.1f}% → {q_new*100:5.1f}%  {arrow} {delta_pp:+.1f}pp  "
            f"({c['trades']} сд.)"
        )
    n_pos = sum(1 for c in categories if c['pnl'] > 0)
    total_pnl = sum(c['pnl'] for c in categories)
    lines.append(f"  [WHEEL] Итог окна: {len(categories)} категорий, прибыльных {n_pos}, "
                 f"суммарный PnL {total_pnl:+,.0f} ₽ | ниже min_trades({min_trades}): "
                 f"{sum(1 for c in categories if min_trades and c['trades'] < min_trades)}"
                 f"{' — ВНИМАНИЕ: скорить нечего, квоты НЕ меняются' if min_trades and all(c['trades'] < min_trades for c in categories) else ''}")
    return lines


def calculate_steering_wheel_quotas(strategies_data, current_quotas, steering_cfg):
    """
    Расчёт квот с усилением лидеров (Power Law).
    score_mode:
      'pnl'         — абсолютная прибыль за окно (как Strategy Tree);
      'pnl_per_lot' — УДЕЛЬНАЯ прибыль: PnL / объём лотов (₽ за лот) — режим штурвала;
      'sharpe'      — pnl / std прибыли на сделку.
    min_trades: категория с меньшим числом сделок за окно не оценивается
    (удельная метрика на 1–2 сделках = шум) и получает min_q.
    Категории без сделок за окно тоже получают min_q — объём уходит в зелёные.
    Финальная нормализация гарантирует сумму = 1.0.
    """
    gamma = steering_cfg.get('gamma', 1.5)
    min_q = steering_cfg.get('min_q', 0.01)
    max_q = steering_cfg.get('max_q', 0.5)
    alpha = steering_cfg.get('alpha', 0.3)
    score_mode = steering_cfg.get('score_mode', 'pnl')
    min_trades = int(steering_cfg.get('min_trades', 0) or 0)
    # V0 = score_volume_prior (shrinkage знаменателя): score = PnL / (volume + V0);
    # если 0 -> авто-медиана объёма по оцениваемым категориям окна.
    v_prior = (float(steering_cfg.get('score_volume_prior', 0.0) or 0.0) or float(np.median([float(_s.get("volume", 0) or 0.0) for _s in strategies_data if isinstance(_s, dict) and _s.get("id") is not None and (not min_trades or int(_s.get("trades", 0) or 0) >= min_trades) and float(_s.get("volume", 0) or 0.0) > 0] or [0.0]))) if score_mode == 'pnl_per_lot' else 0.0

    # ── 1. Сырые баллы с усилением Power Law ──
    scores = []
    for s in strategies_data:
        if not isinstance(s, dict):
            continue

        sid = s.get("id")
        if sid is None:
            continue

        pnl_raw = s.get("pnl", 0) or 0.0
        n_trades = int(s.get("trades", 0) or 0)

        # Мало сделок за окно → удельная метрика это шум: категория не
        # оценивается и получает минимум (объём уходит в зелёные зоны).
        if min_trades and n_trades < min_trades:
            scores.append((sid, 0.0))
            continue

        if score_mode == 'pnl_per_lot':
            vol_lots = float(s.get("volume", 0) or 0.0)
            score = (max(float(pnl_raw), 0.0) / (vol_lots + v_prior)) if vol_lots > 0 else 0.0
        elif score_mode == 'sharpe':
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

    # ── 3. Стратегии БЕЗ сделок за окно → минимум (нет прибыли = нет объёма) ──
    # (раньше сохраняли текущую долю — это ломало синхрон с деревом)
    scored_ids = set(target_weights.keys())
    base_share = 1.0 / len(current_quotas) if current_quotas else 0.0
    for sid in current_quotas:
        if sid not in scored_ids:
            new_quotas[sid] = min_q  # нет сделок за окно → нет прибыли → минимум (объём уходит в зелёные)

    # ── 4. Финальная нормализация к 1.0 ──
    total = sum(new_quotas.values())
    if total > 0:
        new_quotas = {k: v / total for k, v in new_quotas.items()}
    else:
        n = len(new_quotas)
        if n > 0:
            new_quotas = {k: 1.0 / n for k in new_quotas}

    # ── 5. ЖЁСТКИЙ ПОТОЛОК (water-filling) ──
    # Наивная нормировка выше могла поднять лидера ВЫШЕ max_q (пол min_q
    # меняет сумму). Итерируем нормировку и clamp, пока потолок не соблюдён
    # точно: ни одна категория не берёт больше max_q, сумма = 1.0.
    _n = len(new_quotas)
    if _n > 0:
        _cap = max_q if max_q * _n >= 1.0 else (1.0 / _n)  # недостижимый потолок не ломает сумму
        for _ in range(50):
            _tot = sum(new_quotas.values())
            if _tot <= 0:
                new_quotas = {k: 1.0 / _n for k in new_quotas}
                break
            _norm = {k: v / _tot for k, v in new_quotas.items()}
            _clamped = {k: max(min_q, min(_cap, v)) for k, v in _norm.items()}
            if all(abs(_clamped[k] - _norm[k]) < 1e-12 for k in _norm):
                new_quotas = _clamped
                break
            new_quotas = _clamped

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


def tree_weighted_lots(items, categories, quota, min_lot=0.01, gamma=1.5, min_trades=5,
                       floor_mult=0.25, ceil_mult=3.0):
    """Обёртка: SOFT-SLOPE версия (база = BT score, множитель категории — от реальных сделок)."""
    return _soft_weighted_lots(items, categories, quota, min_lot=min_lot,
                               min_trades=min_trades, floor_mult=floor_mult,
                               ceil_mult=ceil_mult)


def _soft_weighted_lots(items, categories, quota, min_lot=0.01,
                        min_trades=5, floor_mult=0.25, ceil_mult=3.0):
    """SOFT-SLOPE: бэктест задаёт КОГО и базовый вес, реальные сделки — множитель объёма.

    Множитель категории m:
      - нет сделок за окно / меньше min_trades -> 1.0 (нейтрально, без наказания);
      - ₽/лот >= 0                            -> 1.0 .. ceil_mult (плавно, сатурация);
      - ₽/лот <  0                            -> floor_mult .. 1.0 (плавно, сатурация).
    Вес стратегии W = BT score × m_категории.
    Лот_i = quota × W_i / Σ(W_j × sl_money_j).
    Никто не обнуляется: даже красные сохраняют долю floor_mult от базового веса.
    """
    cats = categories or {}

    # удельная метрика ₽/лот по категории (None = нет данных / мало сделок)
    raw = {}
    for sid, c in cats.items():
        vol = float(c.get('volume') or 0.0)
        pnl = float(c.get('pnl') or 0.0)
        tr = int(c.get('trades') or 0)
        raw[sid] = (pnl / vol) if (vol > 0 and tr >= min_trades) else None

    # авто-масштаб: типичный |₽/лот| среди оценённых категорий
    vals = [abs(v) for v in raw.values() if v is not None and v != 0.0]
    if vals:
        scale = float(np.median(vals))
        if scale <= 0:
            scale = 1.0
    else:
        scale = 1.0

    m = {}
    for sid in cats:
        v = raw.get(sid)
        if v is None:
            m[sid] = 1.0
        elif v >= 0:
            m[sid] = 1.0 + (ceil_mult - 1.0) * (v / (v + scale))
        else:
            m[sid] = 1.0 - (1.0 - floor_mult) * (abs(v) / (abs(v) + scale))

    # вес стратегии = BT score × множитель её категории
    W = {}
    for it in items:
        sc = max(float(it.get('score') or 0.0), 0.0)
        W[it.get('key')] = sc * m.get(it.get('sid'), 1.0)

    denom = 0.0
    for it in items:
        denom += W.get(it.get('key'), 0.0) * (float(it.get('sl_money') or 0.0))

    lots = {}
    for it in items:
        k = it.get('key')
        slm = float(it.get('sl_money') or 0.0)
        if denom > 0 and W.get(k, 0.0) > 0 and slm > 0:
            lot = quota * W[k] / denom
        else:
            lot = min_lot
        lots[k] = max(lot, min_lot)
    return lots


def _category_multipliers(categories, min_trades=5, floor_mult=0.25, ceil_mult=3.0):
    """Множитель объёма на категорию из реальных сделок (SOFT-SLOPE)."""
    cats = categories or {}
    raw = {}
    for sid, c in cats.items():
        vol = float(c.get('volume') or 0.0)
        pnl = float(c.get('pnl') or 0.0)
        tr = int(c.get('trades') or 0)
        raw[sid] = (pnl / vol) if (vol > 0 and tr >= min_trades) else None
    vals = [abs(v) for v in raw.values() if v is not None and v != 0.0]
    if vals:
        scale = float(np.median(vals))
        if scale <= 0:
            scale = 1.0
    else:
        scale = 1.0
    m = {}
    for sid in cats:
        v = raw.get(sid)
        if v is None:
            m[sid] = 1.0
        elif v >= 0:
            m[sid] = 1.0 + (ceil_mult - 1.0) * (v / (v + scale))
        else:
            m[sid] = 1.0 - (1.0 - floor_mult) * (abs(v) / (abs(v) + scale))
    return m


def soft_plan_lots(items, categories, quota, min_lot=0.01,
                   min_trades=5, floor_mult=0.25, ceil_mult=3.0):
    """План объёма на день.

    1) Если есть валидный `sl_money` (>0) — абсолютная нормировка к риск-квоте
       (как в live-врезке main.py): lot_i = quota·W_i / Σ(W_j·sl_money_j).
    2) Иначе (терминал недоступен, sl_money=0) — перераспределение УЖЕ имеющегося
       объёма (`base_lot`) по множителю категории с СОХРАНЕНИЕМ суммарного объёма.
       Это относительный превью-план: кто получает больше, кто меньше.
    """
    has_slm = any(float(it.get('sl_money') or 0.0) > 0 for it in items)
    if has_slm and quota and quota > 0:
        return _soft_weighted_lots(items, categories, quota, min_lot=min_lot,
                                   min_trades=min_trades, floor_mult=floor_mult,
                                   ceil_mult=ceil_mult)
    m = _category_multipliers(categories, min_trades, floor_mult, ceil_mult)
    base_total = sum(max(float(it.get('base_lot') or 0.0), 0.0) for it in items)
    if base_total <= 0:
        return {it.get('key'): min_lot for it in items}
    w = {}
    for it in items:
        w[it.get('key')] = max(float(it.get('base_lot') or 0.0), 0.0) * m.get(it.get('sid'), 1.0)
    sw = sum(w.values()) or 1.0
    lots = {}
    for it in items:
        lots[it.get('key')] = max(base_total * w[it.get('key')] / sw, min_lot)
    return lots


def _tree_weighted_lots_hard(items, categories, quota, min_lot=0.01, gamma=1.5, min_trades=5):
    """Поправка объёма: бэктест выбирает КОГО, реальные сделки — СКОЛЬКО.

    items: список dict с ключами:
        'key'      — уникальный ключ стратегии;
        'sid'      — категория 'symbol_family' (напр. 'USDJPYrfd_rf');
        'score'    — score бэктеста (вес внутри категории);
        'sl_money' — деньги риска на 1 лот по SL (нормировка к риск-квоте),
                     может быть None (тогда берётся 1.0).
    categories: dict sid -> {'pnl','volume','trades'} за окно аллокации.

    Вес категории w = (PnL/объём)^gamma, если PnL>0 и trades>=min_trades, иначе 0.
    Доля стратегии внутри категории ∝ score бэктеста.
    Лот_i = quota * W_i / Σ(W_j * sl_money_j).
    Категории с w=0 получают min_lot («убыточные едут на минималке»).

    Возвращает dict key -> lot.
    """
    cats = categories or {}
    w_cat = {}
    for sid, c in cats.items():
        vol = float(c.get('volume') or 0.0)
        pnl = float(c.get('pnl') or 0.0)
        tr = int(c.get('trades') or 0)
        if vol > 0 and pnl > 0 and tr >= min_trades:
            w_cat[sid] = (pnl / vol) ** gamma
        else:
            w_cat[sid] = 0.0

    # Сумма score внутри категории — для доли стратегии
    ssum = {}
    for it in items:
        sid = it.get('sid')
        ssum[sid] = ssum.get(sid, 0.0) + max(float(it.get('score') or 0.0), 0.0)

    # Вклад стратегии: вес категории × доля по бэктесту
    W = {}
    for it in items:
        sid = it.get('sid')
        sc = max(float(it.get('score') or 0.0), 0.0)
        share = (sc / ssum[sid]) if ssum.get(sid, 0.0) > 0 else 1.0
        W[it.get('key')] = w_cat.get(sid, 0.0) * share

    denom = 0.0
    for it in items:
        slm = it.get('sl_money')
        slm = float(slm) if slm else 1.0
        denom += W.get(it.get('key'), 0.0) * (float(it.get('sl_money') or 0.0))

    lots = {}
    for it in items:
        k = it.get('key')
        slm = it.get('sl_money')
        slm = float(slm) if slm else 1.0
        if denom > 0 and W.get(k, 0.0) > 0 and (it.get('sl_money') or 0.0) > 0:
            lot = quota * W[k] / denom
        else:
            lot = min_lot
        lots[k] = max(lot, min_lot)
    return lots


def apply_tree_weighting(active, symbol_data, balance, risk_pct,
                         min_lot=0.01, gamma=1.5, min_trades=5, lookback_days=14):
    """Пересчитать лоты активного набора от реальных сделок (Tree).

    Бэктест выбирает набор; объём задают реальные сделки: зелёные категории →
    больше, красные → min_lot. Меняет r['lot'] на месте. Безопасна: при любой
    ошибке/отсутствии данных оставляет лоты как есть.
    """
    if not active:
        return active
    try:
        from daily_report import get_dashboard_data
        from risk_manager import _sl_money_per_lot
    except Exception:
        return active

    d = get_dashboard_data(lookback_days, manage_connection=False)
    df = (d or {}).get('trades_df')
    if df is None or len(df) == 0:
        return active

    df = df.copy().reset_index(drop=True)
    if 'profit' in df.columns and 'profit_net' in df.columns:
        df = df.drop(columns=['profit'])
    df = df.rename(columns={'profit_net': 'profit'})
    if 'entry' in df.columns:
        def _closing(v):
            if isinstance(v, str):
                return v.strip().lower() == 'out'
            try:
                return int(v) == 1
            except (TypeError, ValueError):
                return False
        df = df[df['entry'].apply(_closing)]
    df['symbol'] = df['symbol'].astype(str)
    df['param_key'] = df['param_key'].astype(str)

    cats = {}
    for c in compute_categories(df):
        cats[c['id']] = c
    if not cats:
        return active

    items = []
    for i, r in enumerate(active):
        info = symbol_data.get(r['symbol'], {}).get('info')
        try:
            slm = _sl_money_per_lot(r['symbol'], info, r.get('sl_points') or 0)
        except Exception:
            slm = None
        items.append({'key': i, 'sid': f"{r['symbol']}_{r.get('type', 'stoch')}",
                      'score': r.get('score'), 'sl_money': slm})

    # Защита: если нет ни одного валидного sl_money (символы не в Market Watch /
    # нет терминала), пересчёт даст знаменатель Σ(W·sl_money)=0 и все лоты схлопнутся
    # в min_lot. В этом случае НЕ трогаем лоты (оставляем из distribute_lots) и выходим.
    if not any(float(it.get('sl_money') or 0.0) > 0 for it in items):
        return active

    lots = tree_weighted_lots(items, cats, balance * risk_pct,
                              min_lot=min_lot, gamma=gamma, min_trades=min_trades)
    for i, r in enumerate(active):
        if lots.get(i):
            r['lot'] = lots[i]
    return active
