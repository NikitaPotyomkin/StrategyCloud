"""Премия и дисконт к объёму по лучшей / худшей тактике входа.

Тактика = пара × день ВЫХОДА сделки. День ВХОДА считается назад по РАБОЧИМ
дням от среднего холда ЭТОЙ пары — та же арифметика, что в лейблах Overview
(выход в среду при холде 3 дня → вход в пятницу, выходные перепрыгиваются).

Правило:
  * лучшая тактика окна  → объём стратегий этой пары × (1 + pct)
  * худшая тактика окна → объём стратегий этой пары × (1 - pct)
  * окно — вся история, но НЕ больше window_days (по умолчанию 90 дней):
    дальше это скользящее окно;
  * связки с < min_trades сделками — шум, в отборе не участвуют;
  * если лучшая и худшая пришлись на ОДНУ пару, надбавки взаимно уничтожаются
    → тильт не применяется вовсе.

Где применяется: В САМОМ КОНЦЕ реранка — в run_steering_wheel() после
перекладки лотов, а также сразу после apply_tree_weighting(). Поэтому в
active_state.json и в Daily Plan уже лежит объём С надбавкой, а не сырой лот.

Идемпотентность: у записи есть маркеры tilt_base / tilt_mult. Повторный вызов
с тем же множителем ничего не меняет (±20% не накапливаются), а если лот
переписал штурвал/дерево — новый лот становится базисом.

Модуль ничего не пишет в торговые файлы, кроме своего отчёта
checkpoints/tactic_tilt.json (его читает Daily Plan в дэшборде).
"""

import json
import os
from datetime import datetime

WINDOW_DAYS_DEFAULT = 90      # «вся история, но не больше 90 дней», дальше — скользящее окно
PCT_DEFAULT = 0.20            # премия/дисконт к объёму
MIN_TRADES_DEFAULT = 2        # связка с 1 сделкой — шум, не тактика
TILT_FILE = 'tactic_tilt.json'
_WD_SHORT = ('пн', 'вт', 'ср', 'чт', 'пт')


# ═══ ПУТИ / МЕЛОЧИ ═══════════════════════════════════════════════════════════
def checkpoint_dir():
    """Каталог checkpoints (создаём: молчаливое отсутствие каталога уже кусало)."""
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'checkpoints')
    os.makedirs(d, exist_ok=True)
    return d


def tilt_path():
    return os.path.join(checkpoint_dir(), TILT_FILE)


def base_symbol(sym):
    """'USDJPYrfd' → 'USDJPY': суффикс счёта не часть тактики (как в дэшборде)."""
    return str(sym).replace('rfd', '')


def entry_weekday(wd_exit, hold_hours):
    """День ВХОДА по дню ВЫХОДА: шаг назад по рабочим дням на round(холд/24).

    Возвращает (индекс дня 0..4, сдвиг в рабочих днях). Рабочие дни, а не
    календарные: холд 24 ч с выходом в понедельник даёт вход в пятницу.
    """
    shift = 0
    try:
        h = float(hold_hours)
    except (TypeError, ValueError):
        h = 0.0
    if h == h and h > 0:
        shift = max(0, min(int(round(h / 24.0)), 4))
    i = int(wd_exit)
    for _ in range(shift):
        i = 4 if i == 0 else i - 1
    return i, shift


# ═══ ДАННЫЕ ══════════════════════════════════════════════════════════════════
def _prepare(window_days):
    """Закрытые сделки окна (не больше window_days) с pair/wd/hold_h."""
    try:
        import pandas as pd
        from daily_report import get_dashboard_data
    except Exception:
        return None
    try:
        d = get_dashboard_data(int(window_days), manage_connection=False)
    except Exception:
        return None
    df = (d or {}).get('trades_df')
    if df is None or len(df) == 0:
        return None
    df = df.copy()
    if 'timestamp' not in df.columns or 'profit_net' not in df.columns \
            or 'symbol' not in df.columns:
        return None
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    cut = pd.Timestamp.now() - pd.Timedelta(days=int(window_days))
    df = df[df['timestamp'] >= cut]
    if df.empty:
        return None
    df['pair'] = df['symbol'].astype(str).map(base_symbol)
    df['wd'] = df['timestamp'].dt.weekday
    df = df[df['wd'] < 5]          # суббота/воскресенье — не торговые дни
    if 'open_time' in df.columns:
        df['hold_h'] = ((df['timestamp'] - pd.to_datetime(df['open_time']))
                        .dt.total_seconds() / 3600.0)
        df.loc[df['hold_h'] < 0, 'hold_h'] = float('nan')
    else:
        df['hold_h'] = float('nan')
    return df


def _compute_tactics_raw(window_days=WINDOW_DAYS_DEFAULT, min_trades=MIN_TRADES_DEFAULT):
    """Лучшая и худшая связка «пара + день выхода».

    Ранг — СУММА PnL связки (как в лейблах Overview): иначе маленькая «плотная»
    связка перебивала бы крупную прибыль.
    """
    res = {'ok': False, 'reason': '', 'window_days': int(window_days),
           'min_trades': int(min_trades), 'combos': 0, 'best': None, 'worst': None}
    df = _prepare(window_days)
    if df is None:
        res['reason'] = 'нет сделок в окне (или данные дашборда недоступны)'
        return res
    hold = {}
    try:
        hold = {str(k): v for k, v in df.groupby('pair')['hold_h'].mean().items()}
    except Exception:
        hold = {}
    agg = {'pnl': ('profit_net', 'sum'), 'trades': ('profit_net', 'count')}
    if 'volume' in df.columns:
        agg['lots'] = ('volume', 'sum')
    c = df.groupby(['pair', 'wd']).agg(**agg).reset_index()
    if 'lots' not in c.columns:
        c['lots'] = 0.0
    c['per'] = c['pnl'] / c['trades'].where(c['trades'] > 0, 1)
    c = c[c['trades'] >= int(min_trades)]
    if c.empty:
        res['reason'] = f'нет связок с >= {int(min_trades)} сделками'
        return res
    c = c.sort_values('pnl', ascending=False)

    def _pack(row):
        wd_e, shift = entry_weekday(int(row['wd']), hold.get(str(row['pair'])))
        hv = hold.get(str(row['pair']))
        try:
            hv = float(hv)
            if hv != hv:
                hv = None
        except (TypeError, ValueError):
            hv = None
        return {'symbol': str(row['pair']), 'wd_exit': int(row['wd']),
                'wd_entry': int(wd_e), 'shift_days': int(shift),
                'pnl': float(row['pnl']), 'trades': int(row['trades']),
                'per': float(row['per']), 'lots': float(row['lots'] or 0.0),
                'hold_h': hv}

    res['ok'] = True
    res['combos'] = int(len(c))
    res['best'] = _pack(c.iloc[0])
    res['worst'] = _pack(c.iloc[-1])
    return res


_CACHE = {}


def compute_tactics(window_days=WINDOW_DAYS_DEFAULT, min_trades=MIN_TRADES_DEFAULT,
                    use_cache=True):
    """Кэш на КАЛЕНДАРНЫЙ день: штурвал зовётся каждый час, а 90 дней истории
    тянуть каждый час незачем — тактики за день так не меняются."""
    key = (int(window_days), int(min_trades), datetime.now().date().isoformat())
    if use_cache and key in _CACHE:
        return _CACHE[key]
    res = _compute_tactics_raw(window_days=window_days, min_trades=min_trades)
    _CACHE.clear()          # держим только актуальный день
    _CACHE[key] = res
    return res


def tilt_map(tactics, pct=PCT_DEFAULT):
    """{pair: {mult, side, ...}} — премия лучшей паре, дисконт худшей."""
    out = {}
    if not tactics or not tactics.get('ok'):
        return out
    best, worst = tactics.get('best'), tactics.get('worst')
    if best and worst and best['symbol'] == worst['symbol']:
        return {}   # одна пара с двух концов: +20% и −20% взаимно уничтожаются
    if best:
        out[best['symbol']] = dict(best, mult=1.0 + float(pct), side='premium')
    if worst:
        out[worst['symbol']] = dict(worst, mult=1.0 - float(pct), side='discount')
    return out


# ═══ ПРИМЕНЕНИЕ ══════════════════════════════════════════════════════════════
def apply_tactic_tilt(records, when=None, pct=PCT_DEFAULT,
                      window_days=WINDOW_DAYS_DEFAULT,
                      min_trades=MIN_TRADES_DEFAULT, weekday_only=False,
                      min_lot=0.01, skip_in_position=True, tactics=None,
                      persist=True, log=print):
    """Масштабировать lot записей по премии/дисконту тактики (на месте).

    records — список dict с 'symbol' и 'lot' (план `active` или значения
    `active_strategies`). Возвращает отчёт (он же пишется в tilt_path()).
    """
    out = {'ok': False, 'reason': '', 'ts': datetime.now().isoformat(timespec='seconds'),
           'pct': float(pct), 'window_days': int(window_days),
           'min_trades': int(min_trades), 'weekday_only': bool(weekday_only),
           'target_weekday': None, 'combos': 0, 'best': None, 'worst': None,
           'applied': {}, 'n_changed': 0}
    recs = list(records or [])
    if not recs:
        out['reason'] = 'нет активных стратегий'
        return out

    t = tactics if tactics is not None else compute_tactics(window_days, min_trades)
    out.update({'best': t.get('best'), 'worst': t.get('worst'),
                'combos': t.get('combos'), 'ok': bool(t.get('ok')),
                'reason': t.get('reason') or ''})
    wd_target = int((when or datetime.now()).weekday())
    out['target_weekday'] = wd_target

    tmap = tilt_map(t, pct)
    if not tmap:
        if t.get('ok') and t.get('best') and t.get('worst') \
                and t['best']['symbol'] == t['worst']['symbol']:
            out['reason'] = 'лучшая и худшая — одна пара: тильт не применяется'
        _persist(out, persist, log)
        return out

    for r in recs:
        try:
            if skip_in_position and r.get('position') is not None:
                continue   # в позиции лот уже в рынке — объём не трогаем
            tip = tmap.get(base_symbol(r.get('symbol')))
            if not tip:
                continue
            if weekday_only and int(tip['wd_entry']) != wd_target:
                continue
            mult = float(tip['mult'])
            cur = float(r.get('lot') or 0.0)
            if cur <= 0:
                continue   # kill switch: стратегия остановлена — объём не наращиваем
            base, prev = r.get('tilt_base'), r.get('tilt_mult')
            expected = None
            if base is not None and prev is not None:
                expected = round(max(float(base) * float(prev), float(min_lot)), 2)
            if expected is None or abs(cur - expected) > 1e-9:
                base = cur   # лот переписан штурвалом/деревом → он и есть базис
            new = round(max(float(base) * mult, float(min_lot)), 2)
            r['tilt_base'] = float(base)
            r['tilt_mult'] = mult
            r['lot'] = new
            changed = abs(new - float(cur)) > 1e-9
            slot = out['applied'].get(tip['symbol'])
            if slot is None:
                slot = {'mult': mult, 'side': tip['side'],
                        'wd_entry': int(tip['wd_entry']), 'wd_exit': int(tip['wd_exit']),
                        'pnl': float(tip['pnl']), 'trades': int(tip['trades']),
                        'hold_h': tip.get('hold_h'), 'n': 0, 'lot_from': 0.0, 'lot_to': 0.0}
                out['applied'][tip['symbol']] = slot
            slot['n'] += 1
            slot['lot_from'] = round(slot['lot_from'] + float(base), 2)
            slot['lot_to'] = round(slot['lot_to'] + new, 2)
            if changed:
                out['n_changed'] += 1
        except Exception as exc:
            log(f"  [WARN] TILT: запись {r.get('symbol')!r} не обработана: {exc!r}")

    for sym, a in out['applied'].items():
        log(f"  [TILT] {sym} ×{a['mult']:.2f} "
            f"({'премия' if a['side'] == 'premium' else 'дисконт'}): "
            f"вход {_WD_SHORT[a['wd_entry']]}, выход {_WD_SHORT[a['wd_exit']]}, "
            f"{a['trades']} сд., {a['pnl']:+,.0f} ₽ · стратегий {a['n']}, "
            f"лот {a['lot_from']:.2f} → {a['lot_to']:.2f}")

    _persist(out, persist, log)
    return out


def _persist(out, persist, log):
    if not persist:
        return
    try:
        with open(tilt_path(), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    except OSError as exc:
        log(f"  [WARN] {TILT_FILE} не записан: {exc!r}")


def load_tilt():
    """Отчёт последнего тильта (для дэшборда). Пустой dict, если файла нет."""
    try:
        with open(tilt_path(), 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def describe(rec):
    """Короткая строка для дэшборда: премия/дисконт по тактикам."""
    if not rec:
        return ''
    if not rec.get('applied'):
        return ''   # тильт не применён — пусть дэшборд покажет reason, а не «премию»
    out = []
    for key, side in (('best', 'premium'), ('worst', 'discount')):
        t = rec.get(key)
        if not t:
            continue
        pct = float(rec.get('pct') or 0.0) * 100.0
        out.append(f"{'премия' if side == 'premium' else 'дисконт'} "
                   f"{'+' if side == 'premium' else '−'}{pct:.0f}% → "
                   f"{t.get('symbol')} (вход {_WD_SHORT[int(t.get('wd_entry', 0))]}, "
                   f"выход {_WD_SHORT[int(t.get('wd_exit', 0))]}, "
                   f"{int(t.get('trades') or 0)} сд.)")
    return ' · '.join(out)
