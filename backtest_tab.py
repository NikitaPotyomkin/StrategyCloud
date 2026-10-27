"""Вкладка Backtest: журнал полных пересчётов бэктеста.

Источник — checkpoints/backtest_history.jsonl (пишет
functions.append_backtest_history на боевой машине, сюда приезжает через
sync_journals_from_network.py, который ЖУРНАЛЫ СЛИВАЕТ, а не затирает).

В журнал попадают только прогоны, которые ДОЛЖНЫ были пересчитать всю сетку:
  kind='full'       — посчитаны все комбинации плана по всем символам;
  kind='incomplete' — полный пересчёт запускался, но покрытие < 100% (символ упал).
                      Такой прогон маркер last_full_recalc не двигает и показывается
                      оранжевым: молчаливого «ничего не было» больше нет.
Реранк по чекпойнтам (kind='none') в файл не пишется вовсе.

Порядок на вкладке: дата последнего пересчёта → две цифры (сколько прогонов и
средняя длительность) → график → таблица прогонов.
Таблица и цифры рисуются своим HTML, а не st.dataframe/st.metric: у dataframe
текст в canvas, размер шрифта там не увеличить никаким CSS.
"""
import json
import os
from datetime import datetime

import pandas as pd
import streamlit as st

try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:  # без plotly вкладка живёт: остаются дата, цифры и таблица
    PLOTLY_AVAILABLE = False

_HERE = os.path.dirname(os.path.abspath(__file__))
CK_DIR = os.path.join(_HERE, 'checkpoints')
HISTORY_PATH = os.path.join(CK_DIR, 'backtest_history.jsonl')
MARKER_PATH = os.path.join(CK_DIR, 'last_full_recalc.json')

# Цвета — те же, что в dashboard.py, чтобы вкладка не выбивалась.
COL_GREEN_LT = '#3FB950'
COL_ORANGE = '#D29922'
COL_TEXT = '#C9D1D9'
COL_MUTED = '#8B949E'
COL_PANEL = '#1D293D'
COL_GRID = '#30363D'

NUM_COLS = ('elapsed_sec', 'combos', 'combos_done', 'combos_plan',
            'symbols', 'symbols_total', 'results', 'coverage_pct')

# Какие kind показываем: только полные пересчёты (полный и неполный).
SHOWN_KINDS = ('full', 'incomplete')

CHART_HEIGHT = 620

TABLE_CSS = """
<style>
.bt-table { width: 100%; border-collapse: collapse; font-size: 1.12rem;
            font-variant-numeric: tabular-nums; }
.bt-table th { text-align: left; color: #8B949E; font-weight: 600;
               font-size: 1.02rem; padding: 10px 12px;
               border-bottom: 1px solid #30363D; white-space: nowrap; }
.bt-table td { padding: 11px 12px; color: #C9D1D9;
               border-bottom: 1px solid #21262D; }
.bt-table td.num { text-align: right; }
.bt-table th.num { text-align: right; }
.bt-table tr:hover td { background: #1D293D; }
.bt-table td.bad { color: #D29922; }
.bt-stats { display: flex; gap: 34px; margin: 0.1rem 0 0.8rem 0; }
.bt-stats .lbl { color: #8B949E; font-size: 1.02rem; }
.bt-stats .val { color: #C9D1D9; font-size: 1.65rem; font-weight: 700;
                 font-variant-numeric: tabular-nums; }
.bt-stats .val.bad { color: #D29922; }
</style>
"""


def _ru(n):
    """Число с пробелами между тысячами: 60543 → '60 543'."""
    try:
        if pd.isna(n):
            return '—'
        return f"{int(n):,}".replace(',', ' ')
    except (TypeError, ValueError):
        return '—'


def _f(value, digits=2):
    """Число с фиксированной точностью либо прочерк."""
    try:
        if pd.isna(value):
            return '—'
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return '—'


def _read_history():
    """Строки журнала прогонов. Битые строки пропускаем, файла нет — пусто."""
    rows = []
    try:
        with open(HISTORY_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except OSError:
        pass
    return rows


def _read_marker():
    try:
        with open(MARKER_PATH, 'r', encoding='utf-8') as f:
            return (json.load(f) or {}).get('last_full_recalc')
    except (OSError, ValueError, TypeError):
        return None


def _parse_ts(value):
    try:
        return datetime.fromisoformat(str(value)) if value else None
    except (ValueError, TypeError):
        return None


def _runs_frame():
    """Прогоны полного пересчёта: ts, minutes, done, plan, cps, symbols, results."""
    df = pd.DataFrame(_read_history())
    if df.empty:
        return df
    if 'kind' not in df.columns:
        df['kind'] = 'full'
    df['ts'] = pd.to_datetime(df.get('ts'), errors='coerce')
    for col in NUM_COLS:
        if col not in df.columns:
            df[col] = float('nan')
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['ts'])
    # Только полные пересчёты: 'full' — 100% плана, 'incomplete' — запускался, но не покрыл.
    df = df[df['kind'].isin(SHOWN_KINDS)]
    if df.empty:
        return df
    df['is_full'] = df['kind'] == 'full'
    df['minutes'] = df['elapsed_sec'] / 60.0
    df['done'] = df['combos_done'].fillna(df['combos'])
    df['plan'] = df['combos_plan'].fillna(df['combos'])
    df['cps'] = df['done'] / df['elapsed_sec'].replace(0, float('nan'))
    # Покрытие: поле из журнала, иначе считаем сами (старые строки его не имеют).
    _calc = df['done'] / df['plan'].replace(0, float('nan')) * 100.0
    df['cover'] = df['coverage_pct'].fillna(_calc)
    return df.sort_values('ts', ascending=False)


def _stats_html(df):
    """Цифры над графиком: сколько было пересчётов и средняя длительность."""
    full = df[df['is_full']]
    n_full = int(len(full))
    n_bad = int(len(df) - n_full)
    avg_min = full['minutes'].mean() if n_full else float('nan')
    html = (
        TABLE_CSS
        + "<div class='bt-stats'>"
        + f"<div><div class='lbl'>Пересчётов</div>"
          f"<div class='val'>{n_full}</div></div>"
        + f"<div><div class='lbl'>Средняя длительность, мин</div>"
          f"<div class='val'>{_f(avg_min, 1)}</div></div>"
    )
    if n_bad:
        html += (f"<div><div class='lbl'>Неполных (не зачтены)</div>"
                 f"<div class='val bad'>{n_bad}</div></div>")
    return html + "</div>"


def _runs_html(df):
    """Таблица прогонов: дата, длительность, скорость, объём, покрытие."""
    head = ('Дата/время', 'Длительность, мин', 'Комб/с', 'Считано', 'План',
            'Покрытие, %', 'Символов', 'В пуле')
    rows = []
    for _, r in df.iterrows():
        cover_cls = 'num' if r['is_full'] else 'num bad'
        date_txt = r['ts'].strftime('%d.%m.%Y %H:%M')
        if not r['is_full']:
            date_txt = '⚠ ' + date_txt
        tds = (
            f"<td class='{'bad' if not r['is_full'] else ''}'>{date_txt}</td>"
            f"<td class='num'>{_f(r['minutes'], 1)}</td>"
            f"<td class='num'>{_f(r['cps'], 2)}</td>"
            f"<td class='num'>{_ru(r['done'])}</td>"
            f"<td class='num'>{_ru(r['plan'])}</td>"
            f"<td class='{cover_cls}'>{_f(r['cover'], 1)}</td>"
            f"<td class='num'>{_ru(r['symbols'])}</td>"
            f"<td class='num'>{_ru(r['results'])}</td>"
        )
        rows.append(f"<tr>{tds}</tr>")
    ths = ''.join(f"<th class='num'>{h}</th>" if i else f"<th>{h}</th>"
                  for i, h in enumerate(head))
    return ("<table class='bt-table'><thead><tr>" + ths + "</tr></thead><tbody>"
            + ''.join(rows) + "</tbody></table>")


def _chart(df):
    fig = go.Figure()
    # Полный пересчёт — зелёным, неполный — оранжевым: на графике сразу видно,
    # что ночь не покрыла план (раньше такой прогон вообще не попадал на экран).
    for is_full, name, color in ((True, 'Полный', COL_GREEN_LT),
                                 (False, 'Неполный', COL_ORANGE)):
        part = df[df['is_full'] == is_full]
        if part.empty:
            continue
        fig.add_trace(go.Scatter(
            x=part['ts'], y=part['minutes'], mode='markers+lines', name=name,
            line=dict(color=color, width=2),
            marker=dict(size=12, color=color,
                        line=dict(width=0.5, color=COL_PANEL)),
            customdata=part[['done', 'plan', 'cover', 'symbols', 'results']].to_numpy(),
            hovertemplate=(
                '%{x|%d.%m.%Y %H:%M}<br>'
                'Длительность: %{y:.1f} мин<br>'
                'Считано: %{customdata[0]} из %{customdata[1]}<br>'
                'Покрытие: %{customdata[2]:.1f}%<br>'
                'Символов: %{customdata[3]}<br>'
                'В пуле: %{customdata[4]}<extra></extra>'
            ),
        ))
    # Легенда нужна только когда на графике есть оба вида точек.
    two_kinds = df['is_full'].nunique() > 1
    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor=COL_PANEL, plot_bgcolor=COL_PANEL,
        font=dict(color=COL_TEXT, size=15),
        hoverlabel=dict(font=dict(size=15)),
        margin=dict(l=10, r=10, t=20, b=10),
        height=CHART_HEIGHT,
        xaxis=dict(title=dict(text='Дата', font=dict(size=16)),
                   tickfont=dict(size=14), gridcolor=COL_GRID),
        yaxis=dict(title=dict(text='Длительность, мин', font=dict(size=16)),
                   tickfont=dict(size=14), gridcolor=COL_GRID),
        showlegend=two_kinds,
        legend=dict(orientation='h', yanchor='bottom', y=1.01, x=0),
    )
    return fig


def render_backtest_tab():
    """Вся вкладка Backtest: дата, цифры, график, таблица."""
    st.markdown(f"<div style='font-size:1.9rem;font-weight:700;"
                f"color:{COL_TEXT};margin:0 0 0.2rem 0;'>Бэктест пересчётов</div>",
                unsafe_allow_html=True)

    df = _runs_frame()
    marker_dt = _parse_ts(_read_marker())

    # ── Дата последнего пересчёта: единственный «датный» лейбл на вкладке ──
    full_df = df[df['is_full']] if not df.empty else df
    last_ts = None if full_df.empty else full_df['ts'].max()
    if last_ts is None or pd.isna(last_ts):
        last_ts = marker_dt
    if last_ts is not None and not pd.isna(last_ts):
        st.markdown(
            f"<div style='margin:0.1rem 0 0.7rem 0;font-size:1.45rem;"
            f"color:{COL_GREEN_LT};font-weight:600;'>"
            f"Последний полный пересчёт: {last_ts.strftime('%d.%m.%Y %H:%M')}"
            f"</div>",
            unsafe_allow_html=True,
        )

    # Журнал и маркер разошлись — значит данные не синхронизированы с боевой.
    if marker_dt and not full_df.empty:
        _last_dt = full_df['ts'].max().to_pydatetime()
        if abs((marker_dt - _last_dt).total_seconds()) > 300:
            st.warning(f"Маркер last_full_recalc.json ({marker_dt:%d.%m %H:%M}) "
                       f"не совпадает с журналом ({_last_dt:%d.%m %H:%M}) — "
                       f"данные не синхронизированы: "
                       f"`python sync_journals_from_network.py`")

    if df.empty:
        st.info("Полных прогонов пока нет — появятся после ближайшего полного "
                "пересчёта (checkpoints/backtest_history.jsonl).")
        return

    # ── Цифры: сколько пересчётов и средняя длительность ──
    st.markdown(_stats_html(df), unsafe_allow_html=True)

    # ── График, под ним таблица ──
    if PLOTLY_AVAILABLE:
        st.plotly_chart(_chart(df), use_container_width=True,
                        key="backtest_chart")
    else:
        st.caption("Plotly недоступен — график длительности не построен.")

    st.markdown(_runs_html(df), unsafe_allow_html=True)
