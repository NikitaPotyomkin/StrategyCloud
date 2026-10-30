"""Максимальная прибыль за день — ДВА графика: абсолютная (₽) и удельная (₽/лот).

Столбец дня — ПИК потенциальной прибыли за сутки:

    потенциал = equity_текущий − balance_начала_суток − внешние_деньги_к_моменту

То есть реализованное за день + текущий floating, минус пополнения/выводы,
случившиеся в этот день. Поэтому депозит на 100 000 ₽ не превращается в
«прибыль дня», а закрытые убытки остаются в минусе — пик может быть < 0.

Абсолютная: max(потенциала) за день по всем замерам equity_samples.

Удельная:   пик потенциала дня / ПЛАНОВЫЙ объём дня, ₽ на 1.00 ЛОТ, где
            плановый объём = максимум объёма книги за сутки. Знаменатель один
            на день: иначе после трима (книга → 0.01 × N, потенциал тот же)
            ₽/лот задирается в plan_vol/остаток раз и портит медиану дней
            (30.10.2026 — тот же фикс в peak_trim._daily_per_lot).
            Объёмы категорий не складываем: они пикуют в разное время, поэтому
            за сутки — это плановый объём книги, а не сумма максимумов по
            категориям.

Почему не эквити: equity = balance + floating, поэтому пополнение на 200 000 ₽
навсегда сдвигает уровень и дни до/после депозита несравнимы. Обе величины
выше от депозита не зависят.

Выходные (сб/вс) в график не попадают: рынок закрыт, а сэмплер продолжает писать
тот же пятничный floating — иначе суббота с воскресеньем дублировали пятницу.

Никаких закрытий, фиксаций и триггеров — только наблюдение.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import streamlit as st

try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except Exception:
    PLOTLY_AVAILABLE = False

# cashflow импортируется лениво внутри _flows_df: блок не должен падать,
# если MetaTrader5/база недоступны (тогда вычет внешних денег просто отключён).

SRV_OFFSET_H = 3
COL_TEXT = '#C9D1D9'
COL_MUTED = '#8B949E'
COL_GREEN_LT = '#3FB950'
COL_RED_LT = '#F85149'
COL_PANEL = '#161B22'
COL_REF = '#D29922'      # горизонталь «медиана дневных пиков»
# 30.10.2026: опорная линия на графиках — МЕДИАНА дневных пиков (было 75% от
# максимума окна). Это ровно то же число, что в метриках «Медиана пика за день»
# и «Медиана на 1 лот», поэтому линия и лейбл больше не расходятся.

FLOW_CACHE_SEC = 60
_FLOW_CACHE = {'ts': 0.0, 'df': None}


def _dark(fig, height: int):
    fig.update_layout(paper_bgcolor=COL_PANEL, plot_bgcolor=COL_PANEL, height=height,
                      margin=dict(l=10, r=10, t=28, b=10),
                      font=dict(color=COL_TEXT, size=12), showlegend=False)
    fig.update_xaxes(gridcolor='#21262D', zeroline=False, type='category')
    fig.update_yaxes(gridcolor='#21262D', zeroline=False)
    return fig


def _y_range(series, extra=()):
    vals = pd.to_numeric(pd.Series(list(series)), errors='coerce')
    vals = vals[np.isfinite(vals)]
    cand = [float(v) for v in extra if v is not None and np.isfinite(float(v))]
    if not vals.empty:
        cand += [float(vals.min()), float(vals.max())]
    if not cand:
        return None
    lo, hi = min(cand), max(cand)
    if hi <= lo:
        hi = lo + 1.0
    span = hi - lo
    return [lo - span * 0.10, hi + span * 0.18]


def _num(v, nd=0) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return '—'
    return f"{v:,.{nd}f}".replace(',', ' ')


def _flows_df() -> pd.DataFrame:
    """Внешние деньги (пополнения/выводы) для вычета из потенциала дня.

    source='cutoff'/'bootstrap' — это входящий остаток периода учёта, а не
    движение денег внутри суток, поэтому он не вычитается.
    balance_ops.ts хранится как серверное время «под видом UTC», поэтому в
    ts_true переводим его в истинный epoch (минус SRV_OFFSET_H часов), чтобы
    корректно сравнивать с equity_samples.ts.
    """
    now = time.time()
    if _FLOW_CACHE['df'] is not None and (now - _FLOW_CACHE['ts']) < FLOW_CACHE_SEC:
        return _FLOW_CACHE['df']

    recs = []
    try:
        import cashflow as _cashflow
        rows = _cashflow.ops_list(limit=5000)
    except Exception:
        rows = []
    for row in rows:
        try:
            _ts = int(row[0])
            _amt = float(row[1])
            _src = str(row[3] or '')
        except (TypeError, ValueError, IndexError):
            continue
        if _src in ('cutoff', 'bootstrap') or _amt == 0:
            continue
        # У разных источников balance_ops.ts в разной шкале:
        #   'deals'     — deal.time, серверное время «под видом UTC» (сдвиг +3 ч);
        #   'reconcile' — time.time(), обычный epoch (сдвига нет).
        # Приводим к истинному epoch, чтобы сравнивать с equity_samples.ts.
        _shift = 0 if _src in ('reconcile', 'manual') else SRV_OFFSET_H * 3600
        recs.append((_ts - _shift, _amt))

    df = pd.DataFrame(recs, columns=['ts', 'amount'])
    if not df.empty:
        df['ts_true'] = df['ts']          # ts уже приведён к истинному epoch
        # день операции — серверная дата (та же граница суток, что у сэмплов)
        # день операции — серверная дата (та же граница суток, что у сэмплов);
        # для 'deals' ts_true + 3 ч возвращает исходный deal.time, для 'reconcile'
        # — переводит истинный epoch в серверное время.
        df['day'] = pd.to_datetime(df['ts_true'] + SRV_OFFSET_H * 3600,
                                   unit='s', utc=True).dt.date
        df = df.sort_values('ts_true').reset_index(drop=True)

    _FLOW_CACHE['ts'] = now
    _FLOW_CACHE['df'] = df
    return df


def _pct_sfx(p) -> str:
    """« (65%)» — процент выполнения плана; пусто, если пик отрицательный."""
    try:
        _p = float(p)
    except (TypeError, ValueError):
        return ''
    if not np.isfinite(_p):
        return ''
    return f" ({_p:.0f}%)"


def _daily(eq: pd.DataFrame) -> pd.DataFrame:
    """Строка на день: пик потенциальной прибыли от начала суток (₽ и ₽/лот).

    Потенциальная прибыль = equity_текущий − balance_начала_суток − внешние деньги
    = реализованное за день + текущий floating, без пополнений и выводов.
    Это то, что было бы заработано, если бы ты закрыл всё в этот момент.
    """
    df = eq.copy()
    df['ts_dt'] = (pd.to_datetime(df['ts'], unit='s', utc=True)
                   + pd.Timedelta(hours=SRV_OFFSET_H))
    df['day'] = df['ts_dt'].dt.date
    df['equity'] = pd.to_numeric(df.get('balance', 0), errors='coerce') + \
                   pd.to_numeric(df.get('floating_total', 0), errors='coerce')
    df = df[np.isfinite(df['equity']) & np.isfinite(df['floating_total'])]
    if df.empty:
        return df
    _vol_src = (df['floating_volume'] if 'floating_volume' in df.columns
                else pd.Series(np.nan, index=df.index))
    df['vol'] = pd.to_numeric(_vol_src, errors='coerce')
    _npos_src = (df['n_positions'] if 'n_positions' in df.columns
                 else pd.Series(np.nan, index=df.index))
    df['npos'] = pd.to_numeric(_npos_src, errors='coerce')
    df = df.sort_values('ts_dt')

    # Найти balance на начало каждого дня (первая запись за день)
    balance_start = df.groupby('day').first()[['balance']].rename(
        columns={'balance': 'balance_start'})
    balance_start['day'] = balance_start.index

    flows = _flows_df()

    rows = []
    for day, g in df.groupby('day', sort=True):
        # Сб/вс рынок закрыт, выходные в график не берём.
        if day.weekday() >= 5:
            continue
        g = g.reset_index(drop=True)

        # Внешние деньги, уже пришедшие к моменту замера (накопительно за сутки).
        g['ext'] = 0.0
        if not flows.empty:
            _f = flows[flows['day'] == day]
            if len(_f):
                _ft = _f['ts_true'].to_numpy(dtype=np.int64)
                _fcum = np.cumsum(_f['amount'].to_numpy(dtype=float))
                _fidx = np.searchsorted(_ft, g['ts'].to_numpy(dtype=np.int64),
                                        side='right') - 1
                g['ext'] = np.where(_fidx >= 0,
                                    _fcum[np.clip(_fidx, 0, len(_fcum) - 1)], 0.0)

        # Потенциальная прибыль от начала дня: equity - balance_начала_дня - внешние
        b_start = float(balance_start.loc[balance_start['day'] == day,
                                          'balance_start'].iloc[0])
        g['potential_profit'] = g['equity'] - b_start - g['ext']

        # Пик: максимальная потенциальная прибыль за день
        i = int(g['potential_profit'].idxmax())
        _pvol = g['vol'].iloc[i]
        _pnpos = g['npos'].iloc[i]
        _pvol = float(_pvol) if pd.notna(_pvol) else np.nan
        _pnpos = float(_pnpos) if pd.notna(_pnpos) else np.nan

        # Плановый объём дня (_plv) = максимум книги за сутки: знаменатель
        # удельной не должен уменьшаться, когда позиции закрываются или режутся.
        # Иначе после трима (книга → 0.01 × N, а потенциал дня остаётся) ₽/лот
        # задирается в plan_vol/остаток раз (×10-20) и портит медиану дней.
        _mv = g.loc[np.isfinite(g['vol']) & (g['vol'] > 0), 'vol']
        _plv = float(_mv.max()) if len(_mv) else np.nan
        # удельная: только замеры, где объём известен и > 0
        per_lot = np.nan
        per_ts = pd.NaT
        per_fl = np.nan
        per_vol = np.nan
        m = (g['vol'] > 0) & np.isfinite(g['vol']) & np.isfinite(g['potential_profit'])
        if bool(m.any()):
            sub = g[m].copy().reset_index(drop=True)
            sub['per'] = sub['potential_profit'] / _plv
            j = int(sub['per'].idxmax())
            per_lot = float(sub['per'].iloc[j])
            per_ts = sub['ts_dt'].iloc[j]
            per_fl = float(sub['potential_profit'].iloc[j])
            per_vol = float(_plv)   # знаменатель удельной = план объёма дня

        # «Процент выполнения плана»: сколько в итоге взято от пика дня.
        # Закрытие = потенциал на последнем замере суток (закрытое + висящее).
        _peak = float(g['potential_profit'].iloc[i])
        _close = float(g['potential_profit'].iloc[-1])
        _per_close = np.nan
        _mm = g[(g['vol'] > 0) & np.isfinite(g['vol'])]
        if len(_mm):
            _per_close = float(_mm['potential_profit'].iloc[-1] / _plv)
        # Плановый объём дня = максимум объёма книги за сутки: закрытие пары
        # сделок не должно уменьшать знаменатель удельной (иначе ₽/лот задирается
        # и правило трима видит ложный пик). vol_close — объём на последнем замере.
        # план объёма дня уже посчитан выше (_plv) — тот же знаменатель
        plan_vol = _plv
        vol_close = float(_mm['vol'].iloc[-1]) if len(_mm) else np.nan
        per_plan = (float(_mm['potential_profit'].iloc[-1]) / plan_vol
                    if (len(_mm) and plan_vol == plan_vol and plan_vol > 0) else np.nan)
        # пик ≤ 0 — процент не считается: делить не на что (день полностью в минусе)
        _fill = (_close / _peak * 100.0) if _peak > 0 else np.nan
        _per_fill = (_per_close / per_lot * 100.0) if (np.isfinite(per_lot)
                                                      and per_lot > 0) else np.nan

        rows.append({
            'day': day,
            'potential_peak': float(g['potential_profit'].iloc[i]),
            'peak_time': g['ts_dt'].iloc[i],
            'n_samples': int(len(g)),
            'peak_vol': (float(_pvol) if np.isfinite(_pvol) else np.nan),
            'peak_npos': (float(_pnpos) if np.isfinite(_pnpos) else np.nan),
            'per_lot': per_lot,
            'per_time': per_ts,
            'per_fl': per_fl,
            'per_vol': per_vol,
            'balance_start': b_start,
            'ext_flow': float(g['ext'].iloc[-1]),
            'potential_close': _close,
            'per_close': _per_close,
            'plan_vol': plan_vol,
            'vol_close': vol_close,
            'per_plan': per_plan,
            'fill_pct': _fill,
            'per_fill_pct': _per_fill,
        })
    return pd.DataFrame(rows)


def _potential_series(eq: pd.DataFrame) -> list:
    """Ряды потенциала по замерам: [(день, np.array(потенциал), ...)].

    Те же формулы, что в _daily, но нужны сами замеры (а не агрегаты дня):
    без них не посчитать правило «закрыть всё при достижении порога».
    """
    df = eq.copy()
    df['ts'] = pd.to_numeric(df['ts'], errors='coerce')
    df['equity'] = pd.to_numeric(df.get('balance', 0), errors='coerce') + \
                   pd.to_numeric(df.get('floating_total', 0), errors='coerce')
    df = df[np.isfinite(df['equity']) & np.isfinite(df['floating_total'])]
    if df.empty:
        return []
    df['ts_dt'] = (pd.to_datetime(df['ts'], unit='s', utc=True)
                   + pd.Timedelta(hours=SRV_OFFSET_H))
    df['day'] = df['ts_dt'].dt.date
    df = df.sort_values('ts_dt')
    b0 = pd.to_numeric(df.groupby('day')['balance'].first(), errors='coerce')
    flows = _flows_df()

    out = []
    for day, g in df.groupby('day', sort=True):
        if day.weekday() >= 5:
            continue
        g = g.reset_index(drop=True)
        ext = np.zeros(len(g), dtype=float)
        if not flows.empty:
            _f = flows[flows['day'] == day]
            if len(_f):
                _ft = _f['ts_true'].to_numpy(dtype=np.int64)
                _fcum = np.cumsum(_f['amount'].to_numpy(dtype=float))
                _fidx = np.searchsorted(_ft, g['ts'].to_numpy(dtype=np.int64),
                                        side='right') - 1
                ext = np.where(_fidx >= 0,
                               _fcum[np.clip(_fidx, 0, len(_fcum) - 1)], 0.0)
        pot = g['equity'].to_numpy(dtype=float) - float(b0.loc[day]) - ext
        out.append((day, pot))
    return out


def _exit_block(eq: pd.DataFrame) -> None:
    """Ретро-сводка: на каком пороге дня выгоднее было фиксировать всё.

    Порог — квантиль дневных пиков (25/медиана/75/90%), плюс «идеал по сетке».
    Итог дня = потенциал в момент, когда порог достигнут, иначе — потенциал на
    последнем замере суток. После выхода день считается законченным.
    """
    series = _potential_series(eq)
    if not series:
        return
    peaks = np.array([float(np.max(p)) for _d, p in series], dtype=float)
    base = float(sum(float(p[-1]) for _d, p in series))
    n_days = len(series)

    def _total(thr):
        vals, fired = [], 0
        for _d, p in series:
            hit = np.flatnonzero(p >= thr)
            if hit.size:
                vals.append(float(p[hit[0]]))
                fired += 1
            else:
                vals.append(float(p[-1]))
        return float(np.sum(vals)), fired

    rows = []
    for name, q in (('25% пиков', 0.25), ('медиана', 0.50),
                    ('75% пиков', 0.75), ('90% пиков', 0.90)):
        thr = float(np.quantile(peaks, q))
        tot, fired = _total(thr)
        rows.append({'опора': name, 'порог, ₽': thr, 'итог, ₽': tot,
                     'к факту, ₽': tot - base,
                     'сработал': '{}/{}'.format(fired, n_days)})

    lo, hi = float(peaks.min()), float(peaks.max())
    if hi > lo:
        _best_thr, _best_tot = None, float('-inf')
        for thr in np.linspace(lo, hi, 60):
            _t, _fired = _total(float(thr))
            if _t > _best_tot:
                _best_thr, _best_tot = float(thr), _t
        if _best_thr is not None:
            _t, _fired = _total(_best_thr)
            rows.append({'опора': 'идеал по сетке (подгонка)', 'порог, ₽': _best_thr,
                         'итог, ₽': _t, 'к факту, ₽': _t - base,
                         'сработал': '{}/{}'.format(_fired, n_days)})

    res = pd.DataFrame(rows)
    _q = res[~res['опора'].str.contains('идеал')]
    _best = _q.loc[_q['итог, ₽'].idxmax()] if not _q.empty else res.iloc[0]
    _detail = ' · '.join(
        '{} {:,.0f} ₽ → {:+,.0f} ₽'.format(r['опора'], r['порог, ₽'], r['итог, ₽'])
        for _, r in res.iterrows())
    st.markdown(
        "**Ретроспектива по этим дням:** лучше всех сработал бы порог «{}» "
        "({:,.0f} ₽) — прибыль {:+,.0f} ₽ вместо фактических {:+,.0f} ₽ "
        "({:+,.0f} ₽ разницы).".format(
            _best['опора'], _best['порог, ₽'], _best['итог, ₽'], base,
            _best['к факту, ₽']))


def _ref_level(day: pd.DataFrame, ycol: str) -> float:
    """Опорный уровень графика: МЕДИАНА дневных пиков по этой же колонке.

    Совпадает с метрикой над графиком: «Медиана пика за день» для
    'potential_peak' и «Медиана на 1 лот» для 'per_lot' (обе считаются как
    day[col].median(), NaN-дни отбрасываются одинаково). 30.10.2026 заменила
    прежний уровень «75% от максимума окна».
    """
    vals = pd.to_numeric(day[ycol], errors='coerce').dropna()
    return float(vals.median()) if len(vals) else float('nan')


def _bars(day: pd.DataFrame, ycol: str, labels: list, customdata, hover: str,
          title: str, key: str) -> None:
    colors = [COL_GREEN_LT if (np.isfinite(float(v)) and float(v) >= 0) else COL_RED_LT
              for v in day[ycol]]
    fig = go.Figure(go.Bar(
        x=[dt.strftime('%d.%m') for dt in day['day']], y=day[ycol],
        marker_color=colors, marker_line_width=0,
        text=labels, textposition='outside', cliponaxis=False,
        textfont=dict(size=11, color=COL_TEXT),
        customdata=customdata, hovertemplate=hover))
    fig.add_hline(y=0, line_color=COL_MUTED, line_width=1)
    # Горизонтальный пунктир: МЕДИАНА дневных пиков окна — один уровень на все
    # бары, ровно то же число, что в метрике над графиком («Медиана пика за день»
    # / «Медиана на 1 лот»).
    _ref_val = _ref_level(day, ycol)


    fig.add_trace(go.Scatter(
        x=[dt.strftime('%d.%m') for dt in day['day']],
        y=[_ref_val] * len(day),


        mode='lines',
        line=dict(color=COL_REF, width=1.4, dash='dot'),
        marker=dict(size=5, color=COL_REF, symbol='diamond'),
        hovertemplate=('%{x}: медиана дневных пиков = %{y:,.0f}'
                       ' (' + title + ')<extra></extra>')))
    # подпись уровня у левого края — видно без наведения мыши


    if np.isfinite(_ref_val):
        fig.add_annotation(x=0.005, y=_ref_val, xref='paper', yref='y',
                           text='медиана = ' + _num(_ref_val),
                           showarrow=False, xanchor='left', yanchor='bottom',
                           font=dict(color=COL_REF, size=11))
    fig.update_layout(yaxis_title=title)
    fig.update_yaxes(range=_y_range(day[ycol], [0.0]))
    st.plotly_chart(_dark(fig, 400), use_container_width=True, key=key)


def _ctx_line(vol, npos) -> str:
    """Короткая справка «объём X лот · позиций N» для подписи под метрикой."""
    parts = []
    try:
        _v = float(vol)
        if np.isfinite(_v) and _v > 0:
            parts.append(f"объём {_v:.2f} лот")
    except (TypeError, ValueError):
        pass
    try:
        _n = float(npos)
        if np.isfinite(_n) and _n > 0:
            parts.append(f"позиций {int(_n)}")
    except (TypeError, ValueError):
        pass
    return (' · ' + ' · '.join(parts)) if parts else ''


def _ext_line(v) -> str:
    """Поправка «внешние деньги дня: +100 000 ₽» — только если они были."""
    try:
        _v = float(v)
    except (TypeError, ValueError):
        return ''
    if not np.isfinite(_v) or abs(_v) < 0.5:
        return ''
    return f" · внешние деньги дня: {_num(_v)} ₽ (вычтены)"


def trim_banner(data: dict, ref_day: float = None) -> None:
    # ── Красный флаг: правило пик-трима включено (РЕАЛЬНЫЕ закрытия) ──────────
    # Стоит в САМОМ начале: флаг должен быть виден даже когда в equity_samples
    # пусто (тогда ниже срабатывает ранний return и блок бы не отрисовался).
    _pt = None
    try:
        from config import PeakTrimParams as _PeakTrim
        _pt = _PeakTrim()
    except Exception:
        _pt = None
    if _pt is not None and bool(getattr(_pt, 'enabled', False)):
        _ref_txt = (" · медиана ₽/лот из графика ≈ {} ₽/лот".format(_num(ref_day)) if (ref_day is not None and ref_day == ref_day and ref_day > 0) else '')
        try:
            _pp = data.get('pos_peaks_df') if isinstance(data, dict) else None
            if (_pp is not None and not getattr(_pp, 'empty', True)
                    and 'peak_per_lot' in _pp.columns):
                if 'volume' in _pp.columns:
                    # та же отсечка, что в peak_trim._ref: у 0.01 лот ₽/лот врёт
                    _pp = _pp[pd.to_numeric(_pp['volume'], errors='coerce')
                              >= float(getattr(_pt, 'min_ref_volume', 0.0))]
                _today = pd.Timestamp.now().date()
                _from = (_today - pd.Timedelta(
                    days=int(_pt.lookback_days))).isoformat()
                _vals = pd.to_numeric(
                    _pp.loc[(_pp['day'] >= _from)
                            & (_pp['day'] < _today.isoformat()), 'peak_per_lot'],
                    errors='coerce').dropna()
                if ref_day is None and len(_vals):
                    _ref_txt = " · эталон ≈ {} ₽/лот (сделки ≥ {:.2f} лот)".format(
                        _num(float(_vals.max())), float(_pt.min_ref_volume))
        except Exception:
            _ref_txt = (" · медиана ₽/лот из графика ≈ {} ₽/лот".format(_num(ref_day)) if (ref_day is not None and ref_day == ref_day and ref_day > 0) else '')
        _wd = int(getattr(_pt, 'lookback_days', 0) or 0)
        _win_txt = (f"за {_wd} дн." if _wd > 0
                    else "за всю историю (с 29.09.2026)")
        st.error("❗ ПРАВИЛО ПИК-ТРИМА АКТИВНО — реальные закрытия включены: "
                 "все позиции счёта режутся до {:.2f} лот, когда удельный потенциал "
                 "дня дошёл до {:.0f}% медианы ₽/лот {}{} (удельную считаем по "
                 "плановому объёму дня, допуск отклонения ±{:.0f}%). Остаток остаётся до "
                 "своего TP/SL. Выключение: config.PeakTrimParams.enabled = False."
                 .format(_pt.keep_volume, _pt.pct * 100.0, _win_txt,
                         _ref_txt,
                         float(getattr(_pt, 'volume_tolerance_pct', 0.20)) * 100.0))

def trim_live(day) -> None:
    """«check peak live»: где мы СЕЙЧАС относительно исторического максимума ₽/лот.

    Показывает ровно то, что видит правило пик-трима (peak_trim.scan_and_trim):
      • текущая удельная дня = потенциал дня / ПЛАНОВЫЙ объём книги (максимум
        объёма за сутки): закрытие пары сделок знаменатель не уменьшает;
      • эталон = максимум удельной по дням ДО сегодняшнего (без подглядывания);
      • сколько ₽/лот осталось до порога pct и сколько это в деньгах при текущем
        объёме книги.
    Данные — из equity_samples (equity_df), как и сам график: дэш файлы не читает
    и в MT5 за позициями не ходит.
    """
    _pt = None
    try:
        from config import PeakTrimParams as _PeakTrim
        _pt = _PeakTrim()
    except Exception:
        _pt = None
    if _pt is None or not bool(getattr(_pt, 'enabled', False)):
        return
    try:
        if day is None or getattr(day, 'empty', True):
            return
        _d = day.dropna(subset=['per_lot']).copy()
        if _d.empty:
            return
        _today = _d['day'].max()
        _cur = _d[_d['day'] == _today].iloc[0]
        _prev = _d[_d['day'] < _today]
        # Эталон правила = агрегат cfg.ref_quantile по дням ДО сегодня. С 30.10
        # это МЕДИАНА дневных пиков — ровно число из лейбла «Медиана на 1 лот».
        _q = float(getattr(_pt, 'ref_quantile', 0.5) or 0.5)
        _ref = float(_prev['per_lot'].quantile(_q)) if len(_prev) else float(_cur['per_lot'])
        _ref_word = ('медиана' if abs(_q - 0.5) < 1e-9 else
                     ('максимум' if abs(_q - 1.0) < 1e-9 else f'p{_q * 100:.0f}'))
        # Удельная по ПЛАНОВОМУ объёму дня (per_plan) — ровно то, что считает
        # правило: закрытие пары сделок не задирает ₽/лот на остатке книги.
        _per_now = _cur.get('per_plan')
        if _per_now is None or pd.isna(_per_now):
            _per_now = _cur.get('per_close')
        if _per_now is None or pd.isna(_per_now):
            _per_now = _cur.get('per_lot')          # нет «последнего замера» — берём пик
        _per_now = float(_per_now)
        if not pd.notna(_per_now) or not (_ref > 0):
            return
        _pct = float(getattr(_pt, 'pct', 1.00))
        _thr = _pct * _ref
        _ratio = _per_now / _ref
        _pot = float(_cur.get('potential_close') or 0.0)
        # Знаменатель правила — плановый объём дня (max книги за сутки), деньги
        # до порога считаем по нему же; уход текущего объёма от плана показываем.
        _plan = _cur.get('plan_vol')
        _plan = float(_plan) if (_plan is not None and pd.notna(_plan)) else float('nan')
        _vnow = _cur.get('vol_close')
        _vnow = float(_vnow) if (_vnow is not None and pd.notna(_vnow)) else float('nan')
        _tol = float(getattr(_pt, 'volume_tolerance_pct', 0.20))
        _vol = _plan if (np.isfinite(_plan) and _plan > 0) else (
            (_pot / _per_now) if _per_now else float('nan'))
        _vtxt = ''
        if np.isfinite(_plan) and _plan > 0 and np.isfinite(_vnow):
            _dev = (_vnow - _plan) / _plan
            _vtxt = (f" · объём {_vnow:.2f} из плановых {_plan:.2f} лот "
                     f"({_dev * 100:+.0f}%, "
                     + ("в допуске" if abs(_dev) <= _tol else "ВНЕ допуска")
                     + f" ±{_tol * 100:.0f}%)")
        _left = _thr - _per_now
        _head = (f"check peak · последний замер {_today}: {_num(_per_now)} ₽/лот = "
                 f"{_ratio * 100:.0f}% эталона {_num(_ref)} ₽/лот "
                 f"({_ref_word} по дням ДО сегодня)")
        if _left > 0:
            _body = (f" · до порога {_pct * 100:.0f}% ({_num(_thr)} ₽/лот) "
                     f"осталось {_num(_left)} ₽/лот")
            _tail = (f" — при текущем объёме {_vol:.2f} лот это ≈ {_num(_left * _vol)} ₽"
                     if pd.notna(_vol) and _vol > 0 else "")
        else:
            _body = f" · порог {_pct * 100:.0f}% ({_num(_thr)} ₽/лот) ПРОЙДЕН"
            _tail = f" — режем все позиции до {float(getattr(_pt, 'keep_volume', 0.01)):.2f} лот"
        st.caption(_head + _body + _tail + _vtxt)
        st.progress(max(0.0, min(1.0, float(_ratio))))
    except Exception as exc:
        st.caption(f"check peak live: не удалось посчитать ({exc!r})")


def render(data: dict, days_back: int) -> None:
    d = data.get('equity_df') if isinstance(data, dict) else None
    if not PLOTLY_AVAILABLE:
        st.caption("Plotly недоступен — графики максимума прибыли не рисуются.")
        return
    if d is None or getattr(d, 'empty', True):
        st.info("В trades_db.equity_samples нет сэмплов за окно. Их пишет сэмплер "
                "main.py каждые ~300 с (`EQUITY_SAMPLE_INTERVAL_SEC`); если процесс "
                "не работал в этот период — показывать нечего.")
        return
    day = _daily(d)
    if day.empty:
        st.info("В equity_samples нет валидных значений floating_total.")
        return

    # ── Красный флаг: правило пик-трима включено (РЕАЛЬНЫЕ закрытия) ──────────
    # Включение = config.PeakTrimParams.enabled=True. Правило режет позицию до
    # keep_volume, когда её удельная прибыль дошла до pct от пика ₽/лот за окно.
    # Считаем эталон прямо из pos_peaks_df (тот же запрос, что уже сделан в
    # daily_report), чтобы показать живую цифру, а не только параметры.
    try:
        from config import PeakTrimParams as _PeakTrim
        _pt = _PeakTrim()
        if False:  # старый блок-дубль отключён: баннер показан в начале render()
            _ref_txt = (" · медиана ₽/лот из графика ≈ {} ₽/лот".format(_num(ref_day)) if (ref_day is not None and ref_day == ref_day and ref_day > 0) else '')
            _pp = data.get('pos_peaks_df') if isinstance(data, dict) else None
            if (_pp is not None and not getattr(_pp, 'empty', True)
                    and 'peak_per_lot' in _pp.columns):
                if 'volume' in _pp.columns:
                    # та же отсечка, что в peak_trim._ref: у 0.01 лот ₽/лот врёт
                    _pp = _pp[pd.to_numeric(_pp['volume'], errors='coerce')
                              >= float(getattr(_pt, 'min_ref_volume', 0.0))]
                _today = pd.Timestamp.now().date()
                _from = (_today - pd.Timedelta(
                    days=int(_pt.lookback_days))).isoformat()
                _vals = pd.to_numeric(
                    _pp.loc[(_pp['day'] >= _from)
                            & (_pp['day'] < _today.isoformat()), 'peak_per_lot'],
                    errors='coerce').dropna()
                if ref_day is None and len(_vals):
                    _ref_txt = " · эталон ≈ {} ₽/лот (сделки ≥ {:.2f} лот)".format(
                        _num(float(_vals.max())), float(_pt.min_ref_volume))
            if False: st.error("устаревший баннер (per-position) выключен, актуальный — trim_banner "
                     "позиция режется до {:.2f} лот, когда удельная прибыль доходит "
                     "до {:.0f}% пика ₽/лот за {} дн.{} Остаток остаётся в рынке до "
                     "своего TP/SL. Выключение: config.PeakTrimParams.enabled = False."
                     .format(_pt.keep_volume, _pt.pct * 100.0, _pt.lookback_days,
                             _ref_txt,
                         float(getattr(_pt, 'volume_tolerance_pct', 0.20)) * 100.0))
    except Exception:
        pass


    _per = day['per_lot'].dropna()
    _pk = day.loc[day['potential_peak'].idxmax()]
    # Дни, где объём не писался (старые сэмплы до миграции floating_volume), в ₽/лот
    # не попадают: у двух метрик может быть разный период — это не ошибка счёта.
    _n_days = int(len(day))
    _n_per = int(len(_per))

    st.markdown("### Максимальная потенциальная прибыль за день")
    trim_banner(data, float(day['per_lot'].median()))
    trim_live(day)
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Медиана пика за день",
                  f"{_num(float(day['potential_peak'].median()))} ₽"
                  + _pct_sfx(day['fill_pct'].median()),
                  delta_color="off")
        st.caption(f"медиана за {_n_days} торговых дней · лучший день: "
                   f"{_pk['day'].strftime('%d.%m')} "
                   f"в {_pk['peak_time'].strftime('%H:%M')} "
                   f"(баланс начала дня: {_num(float(_pk['balance_start']))} ₽)"
                   + _ctx_line(_pk.get('peak_vol'), _pk.get('peak_npos'))
                   + _ext_line(_pk.get('ext_flow'))
                   + f" · к концу дня {_num(float(_pk['potential_close']))} ₽"
                   + _pct_sfx(_pk.get('fill_pct')) + " от пика")
    with c2:
        if _n_per:
            _pkp = day.loc[day['per_lot'].idxmax()]
            st.metric("Медиана на 1 лот",
                      f"{_num(float(day['per_lot'].median()))} ₽/лот"
                      + _pct_sfx(day['per_fill_pct'].median()),
                      delta_color="off")
            st.caption(f"медиана за {_n_per} дней · лучший день: "
                       f"{_pkp['day'].strftime('%d.%m')} "
                       f"в {_pkp['per_time'].strftime('%H:%M')} · ₽ на 1.00 лот "
                       f"· к концу дня "
                       f"{_num(float(_pkp['per_close']))} ₽/лот"
                       + _pct_sfx(_pkp.get('per_fill_pct')) + " от пика")
        else:
            st.metric("Медиана на 1 лот", "—", delta_color="off")
            st.caption("нет данных об объёме за окно")

    _exit_block(d)

    # ── 1. Абсолютная: максимум потенциальной прибыли за день, ₽ ─────────────
    st.markdown("**Абсолютная — потенциал, ₽** · столбец — пик дня, пунктир — "
                "медиана дневных пиков (горизонталь на все бары)")
    _bars(day, 'potential_peak',
          [_num(float(v)) + _pct_sfx(p) for v, p
           in zip(day['potential_peak'], day['fill_pct'])],
          day[['peak_time', 'n_samples', 'peak_vol', 'peak_npos', 'ext_flow',
               'potential_close', 'fill_pct']].values,
          hover=('%{x}: потенциал %{y:,.0f} ₽<br>'
                 'момент: %{customdata[0]|%H:%M} (%{customdata[1]} замеров)<br>'
                 'объём: %{customdata[2]:.2f} лот · позиций: %{customdata[3]:.0f}<br>'
                 'внешние деньги дня (вычтены): %{customdata[4]:,.0f} ₽<br>'
                 'к концу дня: %{customdata[5]:,.0f} ₽ '
                 '(%{customdata[6]:.0f}% от пика)'
                 '<extra></extra>'),
          title='максимальный потенциал за день, ₽',
          key='risk_profit_peak_day')

    # ── 2. Удельная: максимум потенциальной прибыли на лот за день, ₽/лот ───
    st.markdown("**Удельная — потенциал на 1 лот, ₽/лот** · пунктир — "
                "медиана дневных пиков")
    if _n_per:
        _bars(day, 'per_lot',
              [_num(float(v)) + _pct_sfx(p) for v, p
               in zip(day['per_lot'], day['per_fill_pct'])],
              day[['per_time', 'per_fl', 'per_vol',
                   'per_close', 'per_fill_pct']].values,
              hover=('%{x}: потенциал %{y:,.0f} ₽/лот<br>'
                     'момент: %{customdata[0]|%H:%M} · '
                     '%{customdata[1]:,.0f} ₽ на %{customdata[2]:.2f} лота<br>'
                     'к концу дня: %{customdata[3]:,.0f} ₽/лот '
                     '(%{customdata[4]:.0f}% от пика)'
                     '<extra></extra>'),
              title='максимальный потенциал на лот за день, ₽/лот',
              key='risk_profit_peak_per_lot')
        st.caption(
            "Потенциал = equity_текущий − balance_начала_суток − пополнения/выводы "
            "этого дня. Верхняя цифра — сколько рублей было бы заработано, если бы "
            "ты закрыл всё в лучший момент дня по всему счёту; в подписи видно, при "
            "каком объёме и числе позиций это было. Нижняя — то же самое на "
            "1.00 лот: пик потенциала дня / плановый объём дня (максимум книги "
            "за сутки), поэтому дни сравнимы, а резка не задирает ₽/лот. Замер "
            "раз в ~5 мин; реальный пик мог быть выше; красный столбец — пик ушёл "
            "в минус, зелёный — в плюс; суббота и воскресенье пропущены; "
            "последний столбец — незавершённый "
            "день. В скобках — процент выполнения плана: сколько взято к концу "
            "дня от пика этого дня (закрытие / пик), для дня целиком в минусе "
            "не считается (у медианных метрик в скобках — медиана этих "
            "процентов по дням). Блок ничего не закрывает."
            + (f" ₽/лот считается по {_n_per} из {_n_days} дней: в остальных в "
               f"equity_samples не записан объём (floating_volume = NULL)."
               if _n_per < _n_days else ""))
    else:
        st.info(
            "Удельная прибыль (₽/лот) пока не считается: в equity_samples нет "
            "заполненной колонки `floating_volume` с объёмом открытых позиций. "
            "Колонка добавлена вместе с этим обновлением — сэмплер начнёт её "
            "писать после перезапуска бота, и нижний график заполнится в тот же "
            "день. Старые сэмплы останутся без объёма (NULL) — задним числом его "
            "не восстановить.")
        st.caption(
            "Верхний график — абсолютный потенциал: equity_текущий минус баланс "
            "начала суток и минус пополнения/выводы этого дня, по открытым "
            "позициям за день. Замер раз в ~5 мин, реальный пик мог быть "
            "чуть выше; суббота и воскресенье пропущены; последний столбец — "
            "незавершённый день. Блок ничего не закрывает.")
