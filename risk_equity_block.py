"""Максимальная прибыль за день — ДВА графика: абсолютная (₽) и удельная (₽/лот).

Абсолютная: max(equity_samples.floating_total) за день, где floating_total =
Σ(profit + swap) по ВСЕМ открытым позициям на момент замера.

Удельная:   max(floating_total / floating_volume) за день, ₽ на 1.00 ЛОТ —
            знаменатель берётся из ТОГО ЖЕ замера, поэтому объём и прибыль
            всегда согласованы (категории и сделки пикуют в разное время,
            их объёмы складывать нельзя). На 0.01 лот эта величина в 100 раз
            меньше: 2 345 ₽/лот = 23.45 ₽ на 0.01 лот.

Почему не эквити: equity = balance + floating, поэтому пополнение на 200 000 ₽
навсегда сдвигает уровень и дни до/после депозита несравнимы. Обе величины
выше от депозита не зависят.

Выходные (сб/вс) в график не попадают: рынок закрыт, а сэмплер продолжает писать
тот же пятничный floating — иначе суббота с воскресеньем дублировали пятницу.

Никаких закрытий, фиксаций и триггеров — только наблюдение.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except Exception:
    PLOTLY_AVAILABLE = False

SRV_OFFSET_H = 3
COL_TEXT = '#C9D1D9'
COL_MUTED = '#8B949E'
COL_GREEN_LT = '#3FB950'
COL_RED_LT = '#F85149'
COL_PANEL = '#161B22'


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


def _daily(eq: pd.DataFrame) -> pd.DataFrame:
    """Строка на день: макс. прибыль в ₽ и макс. прибыль на лот (₽/лот)."""
    df = eq.copy()
    df['fl'] = pd.to_numeric(df.get('floating_total'), errors='coerce')
    # Колонки объёма может не быть вовсе (старая БД): тогда пустая серия, а не None.
    _vol_src = (df['floating_volume'] if 'floating_volume' in df.columns
                else pd.Series(np.nan, index=df.index))
    df['vol'] = pd.to_numeric(_vol_src, errors='coerce')
    df = df[np.isfinite(df['fl'])]
    if df.empty:
        return df
    df['ts_dt'] = (pd.to_datetime(df['ts'], unit='s', utc=True)
                   + pd.Timedelta(hours=SRV_OFFSET_H))
    df['day'] = df['ts_dt'].dt.date
    _npos_src = (df['n_positions'] if 'n_positions' in df.columns
                 else pd.Series(np.nan, index=df.index))
    df['npos'] = pd.to_numeric(_npos_src, errors='coerce')
    df = df.sort_values('ts_dt')

    rows = []
    for day, g in df.groupby('day', sort=True):
        # Сб/вс рынок закрыт, но сэмплер продолжает писать тот же пятничный floating —
        # выходные дублировали пятничный максимум. Выходные в график не берём.
        if day.weekday() >= 5:
            continue
        g = g.reset_index(drop=True)
        i = int(g['fl'].idxmax())
        _pvol = g['vol'].iloc[i]      # объём в момент пика (для подписи/проверки)
        _pnpos = g['npos'].iloc[i]    # сколько позиций держало этот пик
        _pvol = float(_pvol) if pd.notna(_pvol) else np.nan
        _pnpos = float(_pnpos) if pd.notna(_pnpos) else np.nan

        # удельная: только замеры, где объём известен и > 0
        per_lot = np.nan
        per_ts = pd.NaT
        per_fl = np.nan
        per_vol = np.nan
        m = (g['vol'] > 0) & np.isfinite(g['vol']) & np.isfinite(g['fl'])
        if bool(m.any()):
            # idxmax() returns an INDEX LABEL, so the subset must have 0..n-1 labels
            # for the .iloc[] lookups below (otherwise: IndexError out-of-bounds).
            sub = g[m].copy().reset_index(drop=True)
            sub['per'] = sub['fl'] / sub['vol']
            j = int(sub['per'].idxmax())
            per_lot = float(sub['per'].iloc[j])
            per_ts = sub['ts_dt'].iloc[j]
            per_fl = float(sub['fl'].iloc[j])
            per_vol = float(sub['vol'].iloc[j])

        rows.append({
            'day': day,
            'fl_peak': float(g['fl'].iloc[i]),
            'peak_time': g['ts_dt'].iloc[i],
            'n_samples': int(len(g)),
            'peak_vol': (float(_pvol) if np.isfinite(_pvol) else np.nan),
            'peak_npos': (float(_pnpos) if np.isfinite(_pnpos) else np.nan),
            'per_lot': per_lot,
            'per_time': per_ts,
            'per_fl': per_fl,
            'per_vol': per_vol,
        })
    return pd.DataFrame(rows)


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

    _per = day['per_lot'].dropna()
    _pk = day.loc[day['fl_peak'].idxmax()]
    # Дни, где объём не писался (старые сэмплы до миграции floating_volume), в ₽/лот
    # не попадают: у двух метрик может быть разный период — это не ошибка счёта.
    _n_days = int(len(day))
    _n_per = int(len(_per))

    st.markdown("### Максимальная прибыль за день")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Максимум по счёту", f"{_num(float(_pk['fl_peak']))} ₽",
                  delta_color="off")
        st.caption(f"лучший день: {_pk['day'].strftime('%d.%m')} "
                   f"в {_pk['peak_time'].strftime('%H:%M')}"
                   + _ctx_line(_pk.get('peak_vol'), _pk.get('peak_npos')))
    with c2:
        if _n_per:
            _pkp = day.loc[day['per_lot'].idxmax()]
            st.metric("Максимум на 1 лот", f"{_num(float(_pkp['per_lot']))} ₽/лот",
                      delta_color="off")
            st.caption(f"лучший день: {_pkp['day'].strftime('%d.%m')} "
                       f"в {_pkp['per_time'].strftime('%H:%M')} · ₽ на 1.00 лот "
                       f"(на 0.01 лот — ×0.01)")
        else:
            st.metric("Максимум на 1 лот", "—", delta_color="off")
            st.caption("нет данных об объёме за окно")

    # ── 1. Абсолютная: максимум прибыли за день, ₽ ─────────────────────────
    st.markdown("**Абсолютная — максимум по счёту, ₽**")
    _bars(day, 'fl_peak',
          [_num(float(v)) for v in day['fl_peak']],
          day[['peak_time', 'n_samples', 'peak_vol', 'peak_npos']].values,
          hover=('%{x}: максимум %{y:,.0f} ₽<br>'
                 'момент: %{customdata[0]|%H:%M} (%{customdata[1]} замеров)<br>'
                 'объём: %{customdata[2]:.2f} лот · позиций: %{customdata[3]:.0f}'
                 '<extra></extra>'),
          title='максимальная прибыль за день, ₽',
          key='risk_profit_peak_day')

    # ── 2. Удельная: максимум прибыли на лот за день, ₽/лот ────────────────
    st.markdown("**Удельная — максимум на 1 лот, ₽/лот**")
    if _n_per:
        _bars(day, 'per_lot',
              [_num(float(v)) for v in day['per_lot']],
              day[['per_time', 'per_fl', 'per_vol']].values,
              hover=('%{x}: максимум %{y:,.0f} ₽/лот<br>'
                     'момент: %{customdata[0]|%H:%M} · '
                     'прибыль %{customdata[1]:,.0f} ₽ на %{customdata[2]:.2f} лота'
                     '<extra></extra>'),
              title='максимальная прибыль на лот за день, ₽/лот',
              key='risk_profit_peak_per_lot')
        st.caption(
            "Обе цифры — НЕреализованный floating (profit + swap по открытым "
            "позициям), а не закрытый результат дня. Верхняя — сколько рублей "
            "висело в плюсе в лучший замер дня по всему счёту; в подписи видно, "
            "при каком объёме и числе позиций это было. Нижняя — то же самое на "
            "1.00 лот: max(floating / объём) по замерам дня, поэтому дни с разным "
            "объёмом сравнимы между собой. Замер раз в ~5 мин, реальный пик мог "
            "быть выше; суббота и воскресенье пропущены; последний столбец — "
            "незавершённый день. Блок ничего не закрывает."
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
            "Верхний график — абсолютная прибыль: максимум Σ(profit + swap) по "
            "открытым позициям за день. Замер раз в ~5 мин, реальный пик мог быть "
            "чуть выше; суббота и воскресенье пропущены; последний столбец — "
            "незавершённый день. Блок ничего не закрывает.")
