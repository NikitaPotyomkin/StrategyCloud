import streamlit as st
import pandas as pd
import numpy as np
import os
import json
import re
from datetime import datetime, timedelta

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

from daily_report import get_dashboard_data

# ── Период аллокации (ЖЁСТКИЙ, из config) ──
# Strategy Tree и Wheel ВСЕГДА считают прибыль за этот период — это окно,
# по которому ночью реально перекладывается объём. Слайдер его НЕ меняет.
from config import SteeringParams as _SteeringParams
ALLOC_DAYS = _SteeringParams().lookback_days

# Дата старта активной торговли фонда (Fund Age в Overview).
# Импорт защищён: на стенде может лежать старый config.py без этой константы,
# и тогда дэшборд лучше показать с фолбэком, чем упасть целиком.
try:
    from config import FUND_START_DATE
except ImportError:  # pragma: no cover
    FUND_START_DATE = '2026-09-29'

# ── Палитра (институциональная) ──
COL_BG       = '#1D293D'   # rgb(29, 41, 61) — фон приложения
COL_PANEL    = '#1D293D'   # rgb(29, 41, 61) — заливки графиков/панелей
COL_TEXT     = '#C9D1D9'
COL_MUTED    = '#8B949E'
COL_GREEN    = '#2EA043'
COL_GREEN_LT = '#3FB950'
COL_RED      = '#DA3633'
COL_RED_LT   = '#F85149'
COL_BLUE     = '#388bfd'
COL_AMBER    = '#D29922'
COL_GRID     = '#30363D'
COL_NAVY     = '#1F2A3A'

st.set_page_config(page_title="Strategy Cloud — Terminal", layout="wide")

# ── Единый шрифт дашборда: Space Grotesk (Google Fonts) ──
# Ставим его и в переменную Streamlit, и в сами элементы: часть виджетов
# (metric, dataframe, tabs, кнопки) задаёт font-family жёстко, одного body мало.
# Цифры — табличные (tabular-nums), иначе колонки в таблицах «пляшут».
# Откат: удалить этот блок (шрифт вернётся к прежнему SF Mono/Consolas).
# code/pre намеренно НЕ трогаем — блоки кода остаются моноширинными.
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&display=swap');

:root, html, body, .stApp, [class*="css"], .stMarkdown, .stMetric, .stDataFrame,
.stCaption, .stText, h1, h2, h3, h4, h5, h6, p, span:not([data-testid="stIconMaterial"]), div, label, button, input,
select, textarea, table, th, td,
.stTabs [data-baseweb="tab"], .stButton button, .stExpander summary {
   font-family: 'Space Grotesk', 'Inter', -apple-system, 'Segoe UI', sans-serif !important;
}
.stApp { font-variant-numeric: tabular-nums; }

/* Иконки Streamlit — это лигатурный шрифт 'Material Symbols Rounded':
   <span data-testid="stIconMaterial">keyboard_arrow_down</span> (fontFeatureSettings=liga).
   Глобальный font-family:!important выше подменял и его, поэтому вместо стрелки печатался
   текст лигатуры (напр. `_arrow`) поверх заголовков expander и табов. Возвращаем шрифт иконкам. */
[data-testid="stIconMaterial"] {
   font-family: 'Material Symbols Rounded' !important;
   text-transform: none !important;
   letter-spacing: normal !important;
}
</style>
""", unsafe_allow_html=True)


# ── Кастомный CSS ──
st.markdown("""
<style>
    /* Тёмный фон */
    .stApp { background-color: #1D293D; }
    /* Верхний бар навигации (Deploy, меню бургер) */
    header,
    header > div,
    header > div > div,
    .css-17eq8hm,
    .css-17eq8hm > div,
    .stApp-header,
    .stApp-header > div {
        background-color: #1D293D !important;
    }

    /* Текст */
    .stMarkdown, .stText { color: #C9D1D9; }

    /* Метрики Streamlit */
    [data-testid="stMetricValue"] {
        font-size: 1.5rem;
        font-weight: 600;
        font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
    }
    [data-testid="stMetricDelta"] {
        font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #8B949E;
    }

    /* Табы */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0px;
        background-color: #1D293D;
        border-radius: 0;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 12px 24px;
        background-color: #1D293D;
        color: #8B949E;
        font-size: 0.85rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        border-radius: 0;
        border-bottom: 2px solid transparent;
    }
    .stTabs [aria-selected="true"] {
        color: #C9D1D9 !important;
        background-color: #1D293D;
        border-bottom: 2px solid #388bfd;
    }

    /* Таблицы: принудительный фон для всех вложенных элементов */
    .stDataFrame,
    .stDataFrame > div,
    .stDataFrame > div > div,
    .stDataFrame > div > div > div,
    .stDataFrame [data-testid="stTable"],
    .stDataFrame [data-testid="stTable"] > div,
    [data-testid="stTable"],
    [data-testid="stTable"] > div,
    [data-testid="stTable"] > div > div,
    [data-testid="stTable"] > div > div > div,
    [data-testid="stDataFrame"],
    [data-testid="stDataFrame"] > div,
    [data-testid="stDataFrame"] > div > div,
    .streamlit-container,
    .streamlit-container > div,
    section[data-testid="stVerticalBlock"],
    section[data-testid="stVerticalBlock"] > div,
    div[data-testid="stDataFrame"]:has(> div),
    div[data-testid="stDataFrame"] > div > div {
        background-color: #1D293D !important;
    }
    /* Streamlit Dataframe internal cells */
    .css-145kwl1,
    .css-145kwl1 > div,
    .css-145kwl1 > div > div,
    .css-145kwl1 > div > div > div,
    .css-17ev2iev,
    .css-17ev2iev > div,
    .css-1l0221q,
    .css-1l0221q > div,
    .css-1l0221q > div > div {
        background-color: #1D293D !important;
    }

    /* Сайдбар */
    .stSidebar > div:first-child {
        background-color: #1D293D;
        padding-top: 2rem;
    }

    /* Заголовки */
    h1 {
        font-size: 1.5rem;
        font-weight: 700;
        letter-spacing: -0.01em;
        color: #C9D1D9;
    }
    h2, h3 {
        font-size: 1.1rem;
        font-weight: 600;
        color: #C9D1D9;
        border-bottom: 1px solid #30363D;
        padding-bottom: 0.4rem;
        margin-top: 1.5rem;
    }

    /* Кнопка */
    .stButton > button {
        background-color: #21262D;
        color: #C9D1D9;
        border: 1px solid #30363D;
        border-radius: 6px;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .stButton > button:hover {
        background-color: #30363D;
        border-color: #388bfd;
    }

    /* План по категориям (Strategy Tree): шрифт ×2. Грид st.dataframe рисуется на canvas,
       font-size его не берёт — увеличиваем через zoom на контейнере (у него key='plan_cat_big'). */
    .st-key-plan_cat_big [data-testid="stDataFrame"] {
        zoom: 2;
    }

    /* Strategy Tree, три метрики: цвет задаёт metric_card (инлайновый color),
       поэтому CSS-правила для .st-key-tree_metrics больше не нужны. */






    /* Caption */
    .stCaption {
        font-size: 0.75rem;
        color: #8B949E;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=30)
def load_dashboard_data(days_back=15):
    return get_dashboard_data(days_back)


def make_gradient_colors(values, positive_hex='#2EA043', negative_hex='#DA3633'):
    if not values:
        return []
    abs_vals = [abs(v) for v in values]
    max_abs = max(abs_vals) if max(abs_vals) > 0 else 1

    def hex_to_rgb(h):
        h = h.lstrip('#')
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    pos_base = hex_to_rgb(positive_hex)
    pos_soft = (30, 40, 30)
    neg_base = hex_to_rgb(negative_hex)
    neg_soft = (40, 28, 28)

    colors = []
    for v in values:
        ratio = abs(v) / max_abs
        if v >= 0:
            r = int(pos_soft[0] + (pos_base[0] - pos_soft[0]) * ratio)
            g = int(pos_soft[1] + (pos_base[1] - pos_soft[1]) * ratio)
            b = int(pos_soft[2] + (pos_base[2] - pos_soft[2]) * ratio)
        else:
            r = int(neg_soft[0] + (neg_base[0] - neg_soft[0]) * ratio)
            g = int(neg_soft[1] + (neg_base[1] - neg_soft[1]) * ratio)
            b = int(neg_soft[2] + (neg_base[2] - neg_soft[2]) * ratio)
        colors.append(f'rgb({r}, {g}, {b})')
    return colors


def plotly_dark_layout(fig, height=400):
    """Применяет тёмную институциональную тему к plotly-фигуре."""
    fig.update_layout(
        height=height,
        template='plotly_dark',
        paper_bgcolor=COL_PANEL,
        plot_bgcolor=COL_PANEL,
        font=dict(color=COL_TEXT, family='Space Grotesk, Inter, Segoe UI, sans-serif', size=18),
        margin=dict(l=60, r=60, t=30, b=50),
        coloraxis_colorbar=dict(
            tickfont=dict(size=16, color=COL_MUTED),
            title_font=dict(size=16, color=COL_MUTED),
        ),
        legend=dict(font=dict(size=16)),
    )
    fig.update_xaxes(gridcolor=COL_GRID, zerolinecolor=COL_GRID,
                     tickfont=dict(size=16, color=COL_MUTED),
                     title_font=dict(size=18))
    fig.update_yaxes(gridcolor=COL_GRID, zerolinecolor=COL_GRID,
                     tickfont=dict(size=16, color=COL_MUTED),
                     title_font=dict(size=18))
    return fig


# ── Карточки метрик и выходные ──
_CARD_FONT = "'Space Grotesk', 'Inter', 'Segoe UI', sans-serif"


# ── Рынок открыт/закрыт: по данным брокера, а не по календарю ──
_MKT_SYMBOLS = ('EURUSDrfd', 'EURUSD', 'GBPUSDrfd', 'USDJPYrfd')
_MKT_STALE_MIN = 10      # сессия по расписанию есть, а тика нет дольше — рынок фактически стоит
_SRV_OFFSET_H = 3        # серверное время = UTC+3 (как в Overview и Daily Plan)

# ── Русские подписи дат: одни и те же в Daily Plan и FinStatement ──
# Дни недели индексируются как date.weekday(): пн=0 … вс=6 ('чт', а не 'Thu').
_RU_MONTHS = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
              'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря')
_RU_WEEKDAYS = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')
# Именительный падеж — для заголовков-месяцев («Октябрь 2026»), а не «октября».
_RU_MONTHS_NOM = ('Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь')


def _mql_dow(d):
    """ENUM_DAY_OF_WEEK в MQL5: Sunday=0 … Saturday=6 (у date.weekday(): Monday=0)."""
    return (d.weekday() + 1) % 7


def market_is_open():
    """Открыт ли рынок ПРЯМО СЕЙЧАС. Возвращает (is_open, source).

    Источники по убыванию достоверности:
      1) расписание сессий символа ОТ БРОКЕРА (symbol_info_session_quote/trade) —
         знает про выходные, праздники и клиринговый перерыв, календарь тут не нужен;
      2) свежесть последнего тика — ловит «сессия по расписанию есть, а торговли нет»
         (клиринг, обрыв связи, неторговый день в терминале);
      3) календарный фолбэк (сб/вс = закрыто) — только если терминал недоступен.

    source возвращается наружу и печатается рядом с бейджем: видно, ОТКУДА ответ.
    Никогда не бросает исключение — дэшборд не должен падать из-за индикатора.
    """
    try:
        # Серверные часы в той же шкале, что и tick.time (серверный epoch).
        now_srv = pd.Timestamp.now('UTC').tz_localize(None) + pd.Timedelta(hours=_SRV_OFFSET_H)
        srv_epoch = (now_srv - pd.Timestamp(1970, 1, 1)).total_seconds()
        if MT5_AVAILABLE:
            for sym in _MKT_SYMBOLS:
                try:
                    if mt5.symbol_info(sym) is None:
                        continue
                    tick = mt5.symbol_info_tick(sym)
                    if tick is None:
                        continue
                    age_min = (srv_epoch - tick.time) / 60.0

                    sessions = []
                    for _fn in ('symbol_info_session_quote', 'symbol_info_session_trade'):
                        try:
                            _got = getattr(mt5, _fn)(sym, _mql_dow(now_srv.date()))
                        except Exception:
                            _got = None
                        for _s in _got or ():
                            try:
                                sessions.append((_s.start.hour * 60 + _s.start.minute,
                                                 int(_s.length or 0)))
                            except Exception:
                                continue

                    cur_min = now_srv.hour * 60 + now_srv.minute
                    # сессия может уходить за полночь: 23:00 + 120 мин = 01:00
                    in_sess = any((s0 <= cur_min < s0 + ln)
                                  or (s0 + ln > 1440 and cur_min < s0 + ln - 1440)
                                  for s0, ln in sessions)
                    if sessions:
                        if not in_sess:
                            return False, f"{sym}: вне сессии брокера"
                        if age_min > _MKT_STALE_MIN:
                            return False, f"{sym}: сессия есть, тика нет {age_min:.0f} мин"
                        return True, f"{sym}: сессия брокера, тик {age_min:.0f} мин назад"
                    if age_min <= _MKT_STALE_MIN:
                        return True, f"{sym}: тик {age_min:.0f} мин назад"
                    return False, f"{sym}: последний тик {age_min / 60:.1f} ч назад"
                except Exception:
                    continue
        if now_srv.weekday() >= 5:
            return False, ""
        return True, ""
    except Exception:
        return True, "источник неизвестен"


def metric_card(label, value, color=None, sub=None):
    """Карточка метрики с единой геометрией (замена st.metric в Overview).

    Нативные st.metric в соседних колонках дают разную высоту блока, из-за чего
    подписи встают на разной линии: «P&L Today» уезжал ниже «Balance» и
    «Forecast P&L». Здесь разметка у всех карточек одинаковая (padding, кегль,
    min-height), поэтому подписи выровнены по одной линии.
    """
    color = color or COL_TEXT
    sub_html = (
        f"<div style='font-size:0.75rem;color:{COL_MUTED};margin-top:0.2rem;'>{sub}</div>"
        if sub else ''
    )
    st.markdown(
        "<div style='padding:0;min-height:4.4rem;'>"
        f"<div style='font-size:0.75rem;text-transform:uppercase;letter-spacing:0.08em;"
        f"color:{COL_MUTED};margin-bottom:0.3rem;'>{label}</div>"
        f"<div style='color:{color};font-size:1.5rem;font-weight:600;line-height:1.2;"
        f"font-family:{_CARD_FONT};'>{value}</div>"
        f"{sub_html}</div>",
        unsafe_allow_html=True,
    )


def metric_colored(label, value, delta=None, delta_color=None):
    """metric_card, но цифра красится по знаку значения.

    st.metric не умеет красить само значение (только дельту), поэтому
    «Зелёные / Красные / Перевес» в Strategy Tree идут через этот шим:
    '+' → COL_GREEN_LT, '−'/'-' → COL_RED_LT, ноль/пусто → COL_MUTED.
    Подпись (delta) уходит в sub, delta_color оставлен для совместимости.
    """
    _v = str(value)
    _s = _v.strip()
    if _s.startswith('+'):
        _c = COL_GREEN_LT
    elif _s.startswith('−') or _s.startswith('-'):
        _c = COL_RED_LT
    else:
        _c = COL_MUTED
    metric_card(label, _v, color=_c, sub=(delta or None))


def hide_weekend_gaps(fig, saturday_only=True):
    """Убирает пустые выходные с временных осей (Plotly rangebreaks).

    FX не торгуется в субботу, поэтому между пятницей и понедельником на осях
    были широкие пустые полосы. saturday_only=True — скрываем только субботу,
    воскресный вечерний бар остаётся (часть брокеров открывает рынок
    ~22:00-24:00 server time). saturday_only=False — выходные целиком
    (пятница 23:00 -> понедельник 00:00). Данные не фильтруются — скрывается
    только область оси, поэтому метрики и агрегаты не меняются.
    """
    bounds = ['sat', 'sun'] if saturday_only else ['sat', 'mon']
    fig.update_xaxes(rangebreaks=[dict(bounds=bounds)])
    return fig


def filter_weekends(df, ts_col='timestamp'):
    """Убирает строки за субботу(5) и воскресенье(6) из DataFrame.

    Используется перед построением графиков чтобы не было пустых полос.
    """
    ts = pd.to_datetime(df[ts_col])
    weekday = ts.dt.weekday
    return df[weekday < 5].copy()


def drop_weekends(df, col='timestamp'):
    """Выбрасывает субботу и воскресенье из датафрейма графиков Overview.

    FX в выходные не торгуется, поэтому на осях оставались широкие пустые
    полосы (пятница -> понедельник). Здесь выходные именно удаляются из данных,
    а не обнуляются, и графики строятся без разрывов.
    """
    if df is None or len(df) == 0 or col not in df.columns:
        return df
    days = pd.to_datetime(df[col]).dt.weekday
    return df[days < 5].copy()


# ── Заголовок ──
# REFRESH — прямо НАД лейблом STRATEGY CLOUD: кнопка в отдельной узкой колонке,
# заголовок рендерится следующим рядом (ниже), а не сбоку.
_col_btn, _col_sp = st.columns([1, 5])
with _col_btn:
    if st.button("REFRESH"):
        load_dashboard_data.clear()
        st.rerun()
col_title, col_btn = st.columns([6, 1])
with col_title:
    st.markdown("<h1>STRATEGY CLOUD <span style='color:#8B949E;font-size:0.8rem;font-weight:400'>/ Dashboard</span></h1>", unsafe_allow_html=True)
if False:  # REFRESH перенесён НАД лейблом (см. _col_btn выше) — старый блок не рендерится
    st.write("")
    if st.button("REFRESH"):
        load_dashboard_data.clear()
        st.rerun()

# ── Настройки ──
# ── Статус последнего деплоя (пишет deploy_pull.py на боевой машине) ──
def load_deploy_status():
    """checkpoints/deploy_status.json — последний цикл автодеплоя.
    Файл создаёт deploy_pull.py на боевой машине, сюда приезжает
    через sync_journals_from_network.py (CHECKPOINT_LIGHT_FILES)."""
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      'checkpoints', 'deploy_status.json')
    try:
        with open(_p, 'r', encoding='utf-8') as _f:
            return json.load(_f)
    except (OSError, ValueError):
        return None


def deploy_badge():
    """Одна строка: когда был последний деплой, что уехало, перезапущен ли бот."""
    _st = load_deploy_status()
    if not _st:
        st.caption("📦 Деплой: нет данных (checkpoints/deploy_status.json не синхронизирован)")
        return
    _ts = str(_st.get('ts') or '')
    try:
        _when = datetime.fromisoformat(_ts).strftime('%d.%m %H:%M')
    except ValueError:
        _when = _ts[:16] or '?'
    _ok = bool(_st.get('ok', True))
    if not _ok:
        _color, _state = COL_RED, '✖ ошибка'
    elif _st.get('deployed'):
        _color, _state = COL_GREEN_LT, '✔ выкачен'
    else:
        _color, _state = COL_MUTED, '⏸ без изменений'

    _bits = []
    _from, _to = (_st.get('from') or ''), (_st.get('to') or '')
    _from = _to = ''  # хеши не показываем
        # хеши коммитов (d0f7623 → d32b996) не показываем — пользователю они ничего не говорят
    _n_files = len(_st.get('files') or [])
    if _n_files:
        _bits.append(f"файлов {_n_files}")
    if _st.get('restarted'):
        _bits.append('бот перезапущен')
    _note = (_st.get('note') or '').strip()
    if _note:
        _bits.append(_note)
    _err = (_st.get('error') or '').strip()
    if _err:
        _bits.append(_err[:140])

    _detail = ' · '.join(_bits)
    st.markdown(
        f"<div style='margin:0.35rem 0 0.7rem 0;font-size:0.75rem;line-height:1.45;'>"
        f"<span style='color:{_color};font-weight:600;'>📦 {_state}</span>"
        f"<br><span style='color:{COL_MUTED};'>{_when}</span>"
                + (f"<br><span style='color:{COL_MUTED};'>{_detail}</span>" if _detail else '')
        # старое: одна строка с разделителями — в сайдбар не влезала
        + "</div>",
        unsafe_allow_html=True,
    )


with st.sidebar:
    st.markdown("### Configuration")
    days_back = st.slider("Dashboard lookback (visual, days)", 1, 90, ALLOC_DAYS)

    st.caption("Auto-refresh: 30s")

    # Последний автодеплой на боевой машине (checkpoints/deploy_status.json).
    deploy_badge()








# ── Загрузка данных ──
try:
    data = load_dashboard_data(days_back)
except Exception as _e_data:
    # Падение слоя данных (MT5 / trades.db / журналы) не должно убивать страницу:
    # исключение здесь уносило ВСЕ вкладки — оставался только заголовок.
    st.error(f"⚠ Ошибка загрузки данных дашборда: {_e_data!r}")
    data = None
# Окно периода аллокации (жёсткое) — его используют Strategy Tree и Wheel.
try:
    data_alloc = load_dashboard_data(ALLOC_DAYS)
except Exception as _e_alloc:
    st.warning(f"⚠ Окно аллокации {ALLOC_DAYS} дн. не загрузилось: {_e_alloc!r}")
    data_alloc = None
if data_alloc is None:
    data_alloc = data  # страховка: если окно аллокации не загрузилось, не падаем

# ── Табы ──
tab_overview, tab_tree, tab_finstatement, tab_daily, tab_risk, tab_strategies, tab_steering, tab_backtest = st.tabs([
    "Overview",
    "Strategy Tree",
    "FinStatement",
    "Daily Plan",
    "Risk",
    "Strategies",
    "Wheel",
    "Backtest",


])


# ═══════════════════════════════════════════════════════════════
#  OVERVIEW
# ═══════════════════════════════════════════════════════════════
with tab_overview:
    if not data:
        st.warning("No data. Ensure MT5 terminal is running.")
        st.stop()

    # ── Бейдж: открыт ли рынок прямо сейчас (источник — брокер, не календарь) ──
    # Внешний div задаёт отступ снизу: иначе бейдж «садится» на подпись Balance.
    _mkt_open, _mkt_src = market_is_open()
    _mkt_color = COL_AMBER if _mkt_open else COL_GREEN_LT
    st.markdown(
        f"<div style='margin:0.15rem 0 1.15rem 0;'>"
        f"<span style='display:inline-block;padding:0.3rem 0.75rem;border:1px solid {_mkt_color};"
        f"border-radius:6px;color:{_mkt_color};font-size:0.78rem;font-weight:600;"
        f"text-transform:uppercase;letter-spacing:0.06em;'>"
        f"{'Market is open' if _mkt_open else 'Market is closed'}</span>"
        f"<span style='color:{COL_MUTED};font-size:0.75rem;margin-left:0.6rem;'>{_mkt_src}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

        # индикатор последнего деплоя рендерится только в сайдбаре (см. выше)

    col1, col2, col3 = st.columns(3)
    updated = datetime.fromisoformat(data['updated']).strftime('%H:%M:%S')

    with col1:
        metric_card("Balance", f"{data['balance']:,.0f} RUB")
    with col2:
        today_pnl = 0.0
        if not data['trades_df'].empty:
            SERVER_OFFSET = timedelta(hours=3)
            tu = pd.to_datetime(data['trades_df']['time'], unit='s', utc=True) + SERVER_OFFSET
            ser_today = (pd.Timestamp.now('UTC') + SERVER_OFFSET).date()
            today_trades = data['trades_df'][
                tu.dt.date == ser_today
            ]
            today_pnl = today_trades['profit_net'].sum()
        pnl_color = COL_GREEN_LT if today_pnl >= 0 else COL_RED_LT
        st.markdown(f"""
        <div style="padding: 0;min-height:4.4rem;">
            <div style="font-size: 0.75rem; text-transform: uppercase;
                        letter-spacing: 0.08em; color: {COL_MUTED};
                        margin-bottom: 0.3rem;">P&L Today</div>
            <div style="font-size: 1.5rem; font-weight: 600;
                        font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
                        color: {pnl_color};">{int(today_pnl):,} RUB</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        forecast_pnl = None
        if not data['trades_df'].empty:
            daily_avg = data['trades_df'].groupby(
                data['trades_df']['timestamp'].dt.date
            )['profit_net'].sum().mean()
            if pd.notna(daily_avg):
                forecast_pnl = daily_avg * 21
        if forecast_pnl is not None:
            metric_card("Forecast P&L (30D)", f"{int(forecast_pnl):,} RUB",
                        sub=None)
        else:
            metric_card("Forecast P&L (30D)", "—")

    # ── Вторая строка метрик: доля к выводу + срок жизни фонда ──
    # Геометрия как в верхнем ряду (3 колонки): Fund Age — левый край,
    # Withdrawable — средняя (ровно под P&L Today), третья пустая. Иначе ряды
    # «шашечкой» и подписи не совпадают по вертикали.
    _col_age, _col_wd, _col_blank = st.columns(3)
    with _col_wd:
        # «Доход за период» — сумма profit_net по окну слайдера (Dashboard lookback),
        # ровно та же величина, что и total_profit в daily_report.get_dashboard_data.
        _period_profit = float(data.get('total_profit') or 0.0)
        # Отрицательный период → к выводу 0: выводить нечего, доля с убытка не берётся.
        _withdrawable = max(0.0, _period_profit * 0.10)
        metric_card(
            "Withdrawable",
            f"{int(_withdrawable):,} RUB",
            color=COL_GREEN_LT if _withdrawable > 0 else COL_MUTED,
            sub=f"10% of {days_back}D",
                 # подпись сокращена до "10% of ND" (база P&L убрана по запросу)
        )
    with _col_age:
        try:
            _fund_start = datetime.strptime(str(FUND_START_DATE), '%Y-%m-%d').date()
            _srv_today = (pd.Timestamp.now('UTC') + pd.Timedelta(hours=3)).date()
            _fund_days = max(0, (_srv_today - _fund_start).days)
            _fund_months = int(round(_fund_days / 30.44))  # округлённо, ср. месяц = 30.44 дн.
            metric_card(
                "Fund Age",
                f"{_fund_days} days ({_fund_months}m)",
                sub=f"since {_fund_start.strftime('%d.%m.%Y')}",
            )
        except Exception:
            metric_card("Fund Age", "—")

    st.caption(f"Last update: {updated} | Trades ({days_back}D): {data['total_trades']}")

    # ── Volume + Equity Curve ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        # Раскладка Overview: 1-й ряд — Equity Curve (слева) + Equity Gross (справа),
        # 2-й ряд — Daily Volume (слева) + Trade Scatter (справа). Колонки создаём
        # заранее: контейнер держит своё место в раскладке, порядок заполнения не важен.
        _row1_eq, col_gross = st.columns(2)
        col_eq = _row1_eq
        col_vol, col_scatter = st.columns(2)

        with col_vol:
            st.markdown("### Daily Volume")
            df_daily = filter_weekends(data['trades_df'])
            df_daily['date'] = df_daily['timestamp'].dt.strftime('%Y-%m-%d')
            daily_stats = df_daily.groupby('date').agg(
                volume=('volume', 'sum'),
                trades=('profit_net', 'count'),
            ).reset_index()

            # Градиент по величине объёма: мелкие дни прозрачнее, крупные — плотнее.
            _vmax = float(daily_stats['volume'].max() or 0.0)
            _vmax = _vmax if _vmax > 0 else 1.0
            _vol_colors = [
                f'rgba(63, 185, 80, {0.30 + 0.60 * (v / _vmax):.3f})'
                for v in daily_stats['volume']
            ]
            fig_vol = go.Figure()
            fig_vol.add_trace(go.Bar(
                x=daily_stats['date'], y=daily_stats['volume'],
                name='Volume (lots)',
                marker=dict(color=_vol_colors,
                            line=dict(width=0.5, color='rgba(63, 185, 80, 0.30)')),
                opacity=1.0,
            ))
            fig_vol.add_trace(go.Scatter(
                x=daily_stats['date'], y=daily_stats['trades'],
                name='Trades', mode='lines+markers',
                line=dict(color=COL_BLUE, width=1.8, shape='spline', smoothing=1.0),
                marker=dict(size=4, color=COL_BLUE, line=dict(width=0)),
                yaxis='y2',
            ))
            fig_vol.update_layout(
                # Категориальная ось: иначе Plotly распознаёт строки дат как date-ось
                # и резервирует пустые места под выброшенные выходные (щели между барами).
                xaxis=dict(type='category'),
                yaxis=dict(title='Volume (lots)', side='left', tickformat=',.2f', rangemode='tozero'),
                yaxis2=dict(title='Trades (n)', side='right', overlaying='y',
                            tickformat='d', showgrid=False, rangemode='tozero'),
                legend=dict(orientation='h', y=1.12, x=0),
                bargap=0,
            )
            st.plotly_chart(plotly_dark_layout(fig_vol, 260), use_container_width=True,
                           key="overview_daily_volume")

        with col_eq:
            st.markdown("### Equity Curve")
            df_eq = filter_weekends(data['trades_df']).sort_values('timestamp').reset_index(drop=True); df_eq['seq'] = list(range(len(df_eq)))
            df_eq['cum_pnl'] = df_eq['profit_net'].cumsum()

            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(
                x=df_eq['seq'], y=df_eq['cum_pnl'], customdata=df_eq['timestamp'],
                mode='lines', line=dict(color=COL_GREEN_LT, width=1.5),
                fill='tozeroy',
                fillgradient=dict(
                    type='vertical',
                    colorscale=[
                        [0, 'rgba(218, 54, 51, 0.25)'],
                        [0.5, 'rgba(218, 54, 51, 0.02)'],
                        [0.5, 'rgba(46, 160, 67, 0.02)'],
                        [1, 'rgba(46, 160, 67, 0.25)'],
                    ],
                ),
                hovertemplate='Time: %{customdata}<br>Cum P&L: %{y:,.1f}<extra></extra>',
                name='',
            ))
            fig_eq.add_hline(y=0, line_dash='dot', line_color=COL_MUTED, opacity=0.4)
            st.plotly_chart(plotly_dark_layout(fig_eq, 260).update_xaxes(showticklabels=False, title=''), use_container_width=True,
                           key="overview_equity_curve")

        with col_gross:
            st.markdown("### Equity Gross")
            # Gross = торговый P&L + ВСЕ неторговые движения денег по счёту
            # (пополнения / выводы: DEAL_TYPE_BALANCE и DEAL_TYPE_CREDIT).
            df_g = filter_weekends(data['trades_df']).sort_values('timestamp').reset_index(drop=True)
            df_g['seq'] = list(range(len(df_g)))
            _cash, _gross_src = [], 'MT5 недоступен'
            if MT5_AVAILABLE:
                try:
                    _deals = mt5.history_deals_get(datetime(2020, 1, 1),
                                                   datetime.now() + timedelta(hours=6))
                    for _d in (_deals or ()):
                        if _d.type in (mt5.DEAL_TYPE_BALANCE, mt5.DEAL_TYPE_CREDIT):
                            _cash.append((int(_d.time), float(_d.profit)))
                    _dep = sum(a for _, a in _cash if a > 0)
                    _wd = sum(a for _, a in _cash if a < 0)
                    _gross_src = (f"пополнения {_dep:+,.0f} ₽, выводы {_wd:+,.0f} ₽, "
                                  f"операций {len(_cash)}")
                except Exception as _ge:
                    _gross_src = f"ошибка MT5: {_ge!r}"
            _cash.sort()
            _ci, _cum_cash, _gross = 0, 0.0, []
            for _t in df_g['time']:
                while _ci < len(_cash) and _cash[_ci][0] <= int(_t):
                    _cum_cash += _cash[_ci][1]
                    _ci += 1
                _gross.append(_cum_cash)
            # Кешфлоу относится к моменту СДЕЛКИ: пополнение «встаёт» на ближайшую
            # сделку окна (у нас нет баров между сделками — ось идёт по сделкам).
            df_g['gross'] = df_g['profit_net'].cumsum() + pd.Series(_gross, dtype=float)
            fig_g = go.Figure()
            fig_g.add_trace(go.Scatter(
                x=df_g['seq'], y=df_g['gross'], customdata=df_g['timestamp'],
                mode='lines', line=dict(color=COL_AMBER, width=1.5),
                fill='tozeroy',
                hovertemplate='Time: %{customdata}<br>Gross: %{y:,.1f}<extra></extra>',
                name='',
            ))
            fig_g.add_hline(y=0, line_dash='dot', line_color=COL_MUTED, opacity=0.4)
            st.plotly_chart(plotly_dark_layout(fig_g, 260).update_xaxes(showticklabels=False, title=''),
                            use_container_width=True, key="overview_equity_gross")
            st.caption(f"Торговый P&L + пополнения/выводы: {_gross_src}")

    # ── Trade scatter ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        # Правая колонка 2-го ряда: пишем напрямую в col_scatter. Контейнер колонок
        # создан выше вместе с остальными, поэтому Streamlit держит её место в
        # раскладке — порядок вызовов рисования на позицию уже не влияет.
        _sc = globals()['col_scatter'] if 'col_scatter' in globals() else st.container()
        _sc.markdown("### Trade Scatter")
        df_sorted = filter_weekends(data['trades_df']).sort_values('timestamp').reset_index(drop=True); df_sorted['seq'] = list(range(len(df_sorted)))
        colors = [COL_GREEN_LT if x >= 0 else COL_RED_LT for x in df_sorted['profit_net']]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_sorted['seq'], y=df_sorted['profit_net'],
            mode='markers',
            marker=dict(size=6, color=colors, line=dict(width=0.5, color=COL_PANEL),
                        symbol='diamond'),
            text=df_sorted.apply(
                lambda r: f"{r['symbol']} | PnL: {r['profit_net']:+.2f} | Vol: {r.get('volume', 0):.2f}",
                axis=1),
            hoverinfo='text', name='',
        ))
        fig.add_hline(y=0, line_dash='dot', line_color=COL_MUTED, opacity=0.4)

        # ── Линия тренда (МНК-регрессия P&L по номеру сделки) ──
        # Наклон = средний дрейф результата сделки: >0 — эдж улучшается, <0 — деградирует.
        if len(df_sorted) >= 3:
            _x = df_sorted['seq'].to_numpy(dtype=float)
            _y = df_sorted['profit_net'].to_numpy(dtype=float)
            _slope, _intercept = np.polyfit(_x, _y, 1)
            _fit = _slope * _x + _intercept
            fig.add_trace(go.Scatter(
                x=df_sorted['seq'], y=_fit,
                mode='lines',
                line=dict(color=COL_AMBER, width=2, dash='dash'),
                name=f"Тренд: {_slope:+.2f} ₽/сделку",
                hoverinfo='skip',
            ))
        # Легенда — горизонтально сверху: в узкой колонке вертикальная легенда
        # справа накрывает точки.
        fig.update_layout(hovermode='x unified',
                          legend=dict(orientation='h', y=1.12, x=0, font=dict(size=12)))
        # Высота 260 — как у соседей по ряду (Daily Volume / Equity Curve / Equity Gross).
        _sc.plotly_chart(plotly_dark_layout(fig, 260).update_xaxes(showticklabels=False, title=''), use_container_width=True,
                        key="overview_trade_scatter")


# ═══════════════════════════════════════════════════════════════
#  FINSTATEMENT — подневный P&L с первой даты фонда
# ═══════════════════════════════════════════════════════════════
with tab_finstatement:
    st.markdown("### Daily P&L by month")
    try:
        # Окно берём ШИРЕ слайдера: от FUND_START_DATE до сегодня (в днях).
        _fs_start = datetime.strptime(str(FUND_START_DATE), '%Y-%m-%d').date()
        _fs_today = (pd.Timestamp.now('UTC') + pd.Timedelta(hours=_SRV_OFFSET_H)).date()
        _fs_n = max(1, (_fs_today - _fs_start).days + 1)
        _fs_data = load_dashboard_data(_fs_n) or {}
        _fs_df = _fs_data.get('trades_df')
        if _fs_df is None or _fs_df.empty:
            st.info("No closed trades since the fund start.")
        elif False:  # подневный вид устарел: вкладка считает по месяцам (код удалит tools/dashboard_tabs.py)
            _fs = _fs_df.copy()
            _fs['date'] = (pd.to_datetime(_fs['time'], unit='s', utc=True)
                           + pd.Timedelta(hours=_SRV_OFFSET_H)).dt.date
            # Вечер пятницы (+3ч) уезжает на сб/вс — относим такие сделки к пятнице,
            # иначе удалённые выходные-строки «съедали» P&L и итог не сходился с таблицей.
            _fs['date'] = [_d - timedelta(days=(_d.weekday() - 4) % 7) if _d.weekday() >= 5 else _d
                           for _d in _fs['date']]
            _by = _fs.groupby('date').agg(pnl=('profit_net', 'sum')).reset_index()
            # Дни без сделок показываем нулём, а не пропускаем: иначе в календаре «дырки».
            _cal = pd.DataFrame({'date': [d.date() for d in pd.date_range(_fs_start, periods=_fs_n)]})
            # Выходные не показываем — в таблице только торговые дни.
            _cal = _cal[_cal['date'].map(lambda _d: _d.weekday() < 5)].reset_index(drop=True)
            _by = _cal.merge(_by, on='date', how='left').fillna({'pnl': 0.0})
            _cols = [c for c in ('symbol', 'param_key', 'volume', 'profit_net') if c in _fs.columns]
            _wd = _RU_WEEKDAYS  # дни недели как в Daily Plan: 'чт', а не 'Thu'
            st.caption(f"Fund start {_fs_start.strftime('%d.%m.%Y')} · {_fs_n} days · "
                       f"total P&L {int(_by['pnl'].sum()):,} RUB (net of swap and commission)")
            _cum = 0.0
            for _i, _r in enumerate(_by.itertuples(), start=1):
                _cum += float(_r.pnl)
                _day = _fs[_fs['date'] == _r.date]
                with st.expander(f"{_i:>3}. {_r.date.strftime('%d.%m')} ({_wd[_r.date.weekday()]}) — "
                                 f"P&L {int(_r.pnl):,} RUB · trades {len(_day)} · cum {int(_cum):,} RUB"):
                    if _day.empty:
                        st.caption("No closed trades this day.")
                    else:
                        st.dataframe(_day[_cols].rename(columns={'profit_net': 'PnL'}),
                                     use_container_width=True)
        else:
            _fs = _fs_df.copy()
            _fs['date'] = (pd.to_datetime(_fs['time'], unit='s', utc=True)
                           + pd.Timedelta(hours=_SRV_OFFSET_H)).dt.date
            # Вечер пятницы (+3ч) уезжает на сб/вс — относим такие сделки к пятнице,
            # иначе удалённые выходные-строки «съедали» P&L и итог не сходился с таблицей.
            _fs['date'] = [_d - timedelta(days=(_d.weekday() - 4) % 7) if _d.weekday() >= 5 else _d
                           for _d in _fs['date']]
            _by = _fs.groupby('date').agg(pnl=('profit_net', 'sum'),
                                          trades=('profit_net', 'size')).reset_index()
            # Дни без сделок показываем нулём, а не пропускаем: иначе в календаре «дырки».
            _cal = pd.DataFrame({'date': [d.date() for d in pd.date_range(_fs_start, periods=_fs_n)]})
            # Выходные не показываем — в таблице только торговые дни.
            _cal = _cal[_cal['date'].map(lambda _d: _d.weekday() < 5)].reset_index(drop=True)
            _by = _cal.merge(_by, on='date', how='left')
            _by['pnl'] = _by['pnl'].fillna(0.0).round(0).astype(int)
            _by['trades'] = _by['trades'].fillna(0).astype(int)
            # Порядок строго по дате — cum считается хронологически, как и раньше.
            _by = _by.sort_values('date').reset_index(drop=True)
            _by['cum'] = _by['pnl'].cumsum()
            _by['wd'] = [_RU_WEEKDAYS[d.weekday()] for d in _by['date']]
            _by['ym'] = [(d.year, d.month) for d in _by['date']]

            # ── Сетка «3 месяца в ряд» ──
            # Раньше каждый месяц занимал всю ширину вкладки, хотя колонок в таблице — 4.
            # Теперь месяц = expander в СВОЕЙ колонке: 3 месяца на строку, дальше ряд
            # начинается сам. Генератор один на обе петли ниже, поэтому месяцы-заготовки
            # (Ноябрь/Декабрь/Январь) продолжают текущую строку, а не начинают новую.
            def _fs_cols_gen():
                while True:
                    for _c in st.columns(3, gap="medium"):
                        yield _c
            _fs_grid = _fs_cols_gen()
            _cols = [c for c in ('symbol', 'param_key', 'volume', 'profit_net') if c in _fs.columns]
            st.caption(f"Fund start {_fs_start.strftime('%d.%m.%Y')} · {_fs_n} days · "
                       f"total P&L {int(_by['pnl'].sum()):,} RUB (net of swap and commission)")

            # ── Месяц раскрывается, дни внутри — атомарные строки таблицы ──
            for _mi, ((_y, _m), _g) in enumerate(_by.groupby('ym', sort=True), start=1):
                _g = _g.reset_index(drop=True)
                _mpnl = int(_g['pnl'].sum())
                _mtr = int(_g['trades'].sum())
                _mtitle = f"{_RU_MONTHS_NOM[_m - 1]} {_y}"

                # Итог по месяцу — прямо в заголовке раскрывашки: внутри только дни,
                # и без строки-итога «сколько за месяц» не видно (cum не суммируем —
                # он накопительный). _mpnl/_mtr до этого считались и не использовались.
                _mlabel = (f"{_mtitle} — {_mpnl:+,} ₽ · {_mtr} сд."
                           + ("" if _mtr else " (сделок нет)"))
                _col = next(_fs_grid)
                with _col.expander(_mlabel, expanded=((_y, _m) == _by['ym'].iloc[-1])):
                    _days = pd.DataFrame({
                        '#': range(1, len(_g) + 1),
                        'day': [d.strftime('%d') for d in _g['date']],
                        'weekday': list(_g['wd']),
                        'PnL': [f"{int(v):,}" for v in _g['pnl']],
                        'trades': _g['trades'],
                        'cum': [f"{int(v):,}" for v in _g['cum']],
                    }).set_index('#').rename(columns={
                        'day': 'Date', 'weekday': 'WD', 'PnL': 'PnL, RUB',
                        'trades': 'Trades', 'cum': 'Cum, RUB'})
                    # ── Подытог по неделям (ISO-неделя, по дате сделки) ──
                    # cum НЕ суммируем — он накопительный (это же и в дневных строках).
                    # Неделя ISO: месяц на границе может содержать неполные недели — так и надо.
                    _wk = _g.copy()
                    _wk['iso'] = [d.isocalendar()[1] for d in _wk['date']]
                    _wsum = _wk.groupby('iso').agg(
                        pnl=('pnl', 'sum'), trades=('trades', 'sum'),
                        d0=('date', 'min'), d1=('date', 'max'),
                    ).reset_index()
                    _wk_rows = ''.join(
                        f"<tr><td>W{int(_r['iso'])}</td>"
                        f"<td>{_r['d0'].strftime('%d.%m')}–{_r['d1'].strftime('%d.%m')}</td>"
                        f"<td>{int(_r['pnl']):,}</td>"
                        f"<td>{int(_r['trades'])}</td></tr>"
                        for _, _r in _wsum.iterrows())
                    st.markdown(
                        "<style>"
                        ".fs-wk{border-collapse:collapse;font-size:0.92rem;margin:0.1rem 0 0.7rem 0;}"
                        ".fs-wk th,.fs-wk td{padding:0.12rem 0.5rem;border:0;text-align:right;"
                        "border-bottom:1px solid #21262d;"
                        "font-family:'SF Mono','Consolas',monospace;}"
                        ".fs-wk th{color:#8B949E;font-size:0.7rem;font-weight:600;"
                        "text-transform:uppercase;letter-spacing:0.06em;}"
                        "</style>"
                        "<div style='font-size:0.95rem;color:#8B949E;"
                        "margin:0.3rem 0 0.1rem 0;'>Подытог по неделям</div>"
                        "<table class='fs-wk'><thead><tr><th>Week</th><th>Dates</th>"
                        "<th>PnL, RUB</th><th>Trades</th></tr></thead><tbody>"
                        + _wk_rows + "</tbody></table>",
                        unsafe_allow_html=True,
                    )
                    # ── Итог по месяцу — нижней строкой той же таблицы ──
                    # Вставляем <tfoot> внутрь .fs-tbl: цифры встают ровно под столбцами
                    # PnL/Trades, а не «плавают» отдельной таблицей. cum НЕ суммируем — он
                    # накопительный, поэтому в итоговой строке его нет. colspan=2 — метка
                    # под колонками Date+WD (индекс '#' в to_html отброшен).
                    _mfoot = (
                        "<tfoot><tr class='fs-tot'>"
                        "<td colspan='2' style='text-align:left;color:#8B949E;font-weight:600;'>"
                        "Итого за месяц</td>"
                        f"<td style='text-align:right;font-weight:700;color:#C9D1D9;'>{_mpnl:,}</td>"
                        f"<td style='text-align:right;font-weight:700;color:#C9D1D9;'>{_mtr}</td>"
                        "<td style='text-align:right;'></td>"
                        "</tr></tfoot>"
                    )
                    # Таблица дней — свой HTML, а не st.dataframe: у грида мелкий шрифт
                    # и «шапка/данные по разным краям». Здесь ширина по содержимому,
                    # цифры и заголовки выровнены одинаково (по правому краю).
                    st.markdown(
                        "<style>"
                        ".fs-tbl{border-collapse:collapse;font-size:0.95rem;}"
                        ".fs-tbl th,.fs-tbl td{padding:0.14rem 0.55rem;white-space:nowrap;"
                        "border-bottom:1px solid #21262d;}"
                        ".fs-tbl th{color:#8B949E;font-size:0.7rem;font-weight:600;"
                        "text-transform:uppercase;letter-spacing:0.06em;}"
                        ".fs-tbl td{font-family:'SF Mono','Consolas',monospace;}"
                        ".fs-tbl th,.fs-tbl td{padding:0.14rem 0.55rem!important;"
                        "font-size:0.95rem!important;border:0!important;"
                        "border-bottom:1px solid #21262d!important;}"
                        ".fs-tbl th{font-size:0.72rem!important;color:#8B949E!important;"
                        "background:transparent!important;}"
                        ".fs-tbl tr.fs-tot td{border-top:1px solid #30363D!important;"
                        "border-bottom:0!important;}"

                        "</style>"
                        + "<div style='overflow-x:auto;'>" + _days.to_html(index=False, border=0, classes='fs-tbl', escape=False)
                        .replace('<th>', "<th style='text-align:right;'>")
                        .replace('<td>', "<td style='text-align:right;'>")
                        .replace('</table>', _mfoot + '</table>') + "</div>",
                        unsafe_allow_html=True,
                    )






            # ── Пустые заготовки на будущие месяцы: Ноябрь, Декабрь, Январь ──
            _ly, _lm = _by['ym'].iloc[-1]
            for _k in (1, 2, 3):
                _tot = _lm + _k
                _fy, _fm = _ly + (_tot - 1) // 12, (_tot - 1) % 12 + 1
                _col = next(_fs_grid)
                with _col.expander(f"{_RU_MONTHS_NOM[_fm - 1]} {_fy}"):
                    st.caption("Месяц ещё не начался — сделок нет.")
    except Exception as _e:
        st.caption(f"⚠ FinStatement недоступен: {_e!r}")


# ═══════════════════════════════════════════════════════════════
#  RISK
# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
#  DAILY PLAN
# ═══════════════════════════════════════════════════════════════
with tab_daily:
    if not data:
        st.warning("No data. Ensure MT5 terminal is running.")
        st.stop()



    # ── День, на который разыгрывается план ──
    # Серверное время = UTC+3 (как в Overview). В выходные торговли нет, поэтому
    # суббота/воскресенье показываются как план на понедельник.



    # Дату берём ИЗ ПЛАНА (active_state.json → updated), а не из «сейчас»:
    # иначе лейбл обещает сегодняшний план, даже если пересчёта сегодня не было.
    _plan_day = None
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'journals', 'active_state.json'), 'r', encoding='utf-8') as _pf:
            _plan_day = pd.to_datetime(json.load(_pf).get('updated')).date()
            if pd.isna(_plan_day):     # в файле нет updated — считаем, что даты нет
                _plan_day = None
    except Exception:
        _plan_day = None
    _plan_today = (pd.Timestamp.now('UTC') + pd.Timedelta(hours=3)).date()


    if _plan_day is None:
        _plan_day = _plan_today
    # Расклад в active_state.json — на СЛЕДУЮЩИЙ торговый день, не на текущий.
    _plan_day += timedelta(days=1)
    while _plan_day.weekday() >= 5:
        _plan_day += timedelta(days=1)
    st.markdown(
        f"<div style='font-size:1.7rem;font-weight:700;color:{COL_TEXT};letter-spacing:0.02em;"
        f"margin:-0.2rem 0 0.1rem 0;'>Дневной план на {_plan_day.day} "
        f"{_RU_MONTHS[_plan_day.month - 1]} ({_RU_WEEKDAYS[_plan_day.weekday()]})</div>",







        unsafe_allow_html=True,
    )

    # ── ИСТОЧНИК ПЛАНА: active_state.json (ночной план), НЕ открытые позиции ──
    _act, _plan_meta = [], {}
    try:
        _as_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'journals', 'active_state.json')
        with open(_as_path, 'r', encoding='utf-8') as _as_f:
            _as = json.load(_as_f)
        _act = list(_as.get('strategies') or [])
        _plan_meta = {'updated': _as.get('updated'), 'balance': _as.get('balance'),
                      'quota': _as.get('quota'), 'total': _as.get('total_strategies')}
    except Exception as _e:
        st.caption(f"⚠ План недоступен (journals/active_state.json): {_e!r}")
    if not _act:
        st.info("Нет плана: journals/active_state.json пуст или ещё не пересчитан (ночной прогон).")
        st.stop()
    else:
        from wheel import compute_categories, calculate_steering_wheel_quotas, category_label
        from config import SteeringParams
        _scfg = SteeringParams()

        # ── Tree: PnL/объём по категориям symbol+family за окно аллокации ──
        _cat_by_id = {}
        try:
            _df_src = (data_alloc or data)['trades_df'].copy().reset_index(drop=True)
            if 'profit' in _df_src.columns and 'profit_net' in _df_src.columns:
                _df_src = _df_src.drop(columns=['profit'])
            _df_src = _df_src.rename(columns={'profit_net': 'profit'})
            if 'entry' in _df_src.columns:
                def _is_closing(v):
                    if isinstance(v, str):
                        return v.strip().lower() == 'out'
                    try:
                        return int(v) == 1
                    except (TypeError, ValueError):
                        return False
                _df_src = _df_src[_df_src['entry'].apply(_is_closing)]
            _df_src['symbol'] = _df_src['symbol'].astype(str)
            _df_src['param_key'] = _df_src['param_key'].astype(str)
            for _c in compute_categories(_df_src):
                _cat_by_id[_c['id']] = _c
        except Exception as _e:
            st.caption(f"⚠ Tree-метрики недоступны: {_e!r}")

        # ── Wheel-квоты (текущие — из активных лотов, как в Steering Wheel) ──
        _cur_q, _new_q = {}, {}
        try:
            _df_a = pd.DataFrame(_act)
            # active_state.json уже содержит 'type' — фолбэк на param_key ломает категорию
            if 'type' not in _df_a.columns:
                _df_a['type'] = 'unknown'
            _df_a['sid'] = _df_a['symbol'].astype(str) + '_' + _df_a['type'].astype(str)
            _df_cat = _df_a.groupby(['sid'], as_index=False)['lot'].sum()
            _tot_lot = _df_a['lot'].sum()
            _cur_q = dict(zip(_df_cat['sid'], _df_cat['lot'] / _tot_lot)) if _tot_lot > 0 else {}
            if _cat_by_id:
                _new_q = calculate_steering_wheel_quotas(
                    list(_cat_by_id.values()), _cur_q,
                    {'alpha': _scfg.alpha, 'min_q': _scfg.min_q, 'max_q': _scfg.max_q,
                     'score_mode': _scfg.score_mode, 'min_trades': _scfg.min_trades,
                     'gamma': getattr(_scfg, 'gamma', 1.5),
                     'score_volume_prior': getattr(_scfg, 'score_volume_prior', 0.0),
                     # Политика потерь: чтобы превью штурвала совпадало с боем
                     # (карантин/kill видны в дэшборде, а не только в main.py)
                     'loss_decay': getattr(_scfg, 'loss_decay', 0.25),
                     'kill_pnl_pct': getattr(_scfg, 'kill_pnl_pct', 0.02),
                     'kill_min_trades': getattr(_scfg, 'kill_min_trades', 3),
                     'quota_rub': 0.0},  # превью: рублёвой квоты нет → kill по % не срабатывает
                    known_ids=list(_cur_q.keys()))
        except Exception as _e:
            st.caption(f"⚠ Wheel-квоты недоступны: {_e!r}")

        # ── опционально: риск ₽ на строку (нужен терминал) ──
        _slm = None
        try:
            from risk_manager import _sl_money_per_lot as _slm_fn
            _slm = _slm_fn
        except Exception:
            _slm = None

        _quota = _plan_meta.get('quota') or (data_alloc or data).get('quota', 0.0) or 0.0

        # ── Сборка строк плана ──
        rows = []
        for s in _act:
            sym = s.get('symbol')
            typ = s.get('type') or s.get('family') or 'unknown'  # param_key НЕ фолбэк: категория неизвестна
            pk = s.get('param_key')
            sid = f"{sym}_{typ}"
            cat = _cat_by_id.get(sid, {})
            lot = float(s.get('lot', 0) or 0)
            risk = None
            _m = None
            if _slm is not None:
                try:
                    _info = mt5.symbol_info(sym)
                    _m = _slm(sym, _info, s.get('sl_points') or 0)
                    risk = lot * _m if _m else None
                except Exception:
                    risk = None
            pass  # _m уже посчитан выше; дубль-сброс убран
            _vol = cat.get('volume') or 0.0
            rows.append({
                'status': 'OPEN' if s.get('has_position') else 'flat',
                'symbol': str(sym).replace('rfd', ''),
                'family': typ,
                'category': category_label(sym, typ),
                'sid': sid,
                'param_key': pk,
                'SL': s.get('sl_points'),
                'TP': s.get('tp_points'),
                'lot': lot,
                'risk ₽': risk,
                'sl_money': _m,
                'sym_raw': sym,
                'BT score': s.get('score'),
                'BT PF': s.get('profit_factor'),
                'BT WR %': s.get('win_rate'),
                'BT trades': s.get('n_trades'),
                'Tree PnL ₽': cat.get('pnl'),
                'Tree ₽/лот': (cat.get('pnl') / _vol) if _vol else None,
                'Tree trades': cat.get('trades'),
                'Q cur %': round(_cur_q.get(sid, 0.0) * 100, 1) if _cur_q else None,
                'Q new %': round(_new_q.get(sid, 0.0) * 100, 1) if _new_q else None,
            })
        df_plan = pd.DataFrame(rows)
        df_plan['flag'] = df_plan.apply(
            lambda r: '⚠ убыток в Tree' if (r['Tree PnL ₽'] is not None
                                            and r['Tree PnL ₽'] < 0 and r['lot'] > 0.01) else ('— нет сделок в окне' if (r['Tree PnL ₽'] is None or r['Tree PnL ₽'] != r['Tree PnL ₽']) else ''),
            axis=1)

        # ── Превью поправки: бэктест выбирает КОГО, реальные сделки — СКОЛЬКО ──
        df_plan['Lot (tree)'] = None
        if _cat_by_id:
            try:
                from wheel import tree_weighted_lots
                _items = []
                for _i, _r in df_plan.iterrows():
                    _risk = _r.get('risk ₽')
                    _slm = (_risk / _r['lot']) if (_r['lot'] and _risk) else None
                    _items.append({'key': _i, 'sid': _r.get('sid'),
                                   'score': _r.get('BT score'), 'sl_money': _slm})
                _lots_adj = tree_weighted_lots(
                    _items, _cat_by_id, _quota, min_lot=0.01,
                    gamma=getattr(_scfg, 'gamma', 1.5), min_trades=_scfg.min_trades)
                df_plan['Lot (tree)'] = df_plan.index.map(_lots_adj)
            except Exception as _e:
                st.caption(f"⚠ Не удалось посчитать план: {_e!r}")

        # ── tree_weighting ВКЛ: план = tree-взвешенный объём от реальных сделок ──
        if getattr(_scfg, 'tree_weighting', False) and _cat_by_id:
            if True:  # soft_plan_lots сам выбирает: absolute (sl_money) или перераспределение (base_lot)
                try:
                    from wheel import soft_plan_lots as _twl
                    _items = [{'key': _i, 'sid': _r['sid'], 'score': _r.get('BT score'),
                               'sl_money': _r.get('sl_money'), 'base_lot': _r.get('lot')}
                              for _i, _r in df_plan.iterrows()]
                    _lots_tw = _twl(_items, _cat_by_id, _quota, min_lot=0.01,
                                    # gamma в soft-версии не используется
                                    min_trades=_scfg.min_trades)
                    _newlot = pd.Series(df_plan.index.map(_lots_tw), index=df_plan.index)
                    _ok = _newlot.notna() & (_newlot > 0)
                    # План из active_state.json — уже ИТОГОВЫЙ (пересчитан штурвалом в
                    # main.py). Повторное tree-взвешивание искажало реальную картину
                    # («дэш ≠ бой»), поэтому лот НЕ перезаписываем; красные ниже помечаются.
                    # риск ₽ под новый план-лот
                    df_plan['risk ₽'] = [
                        (l * m) if (m and l) else None
                        for l, m in zip(df_plan['lot'], df_plan['sl_money'])]
                    df_plan['flag'] = df_plan.apply(
                        lambda r: '⚠ убыток в Tree' if (r['Tree PnL ₽'] is not None
                                                        and r['Tree PnL ₽'] < 0 and r['lot'] > 0.01) else ('— нет сделок в окне' if (r['Tree PnL ₽'] is None or r['Tree PnL ₽'] != r['Tree PnL ₽']) else ''),
                        axis=1)
                except Exception as _e2:
                    st.caption(f"⚠ tree_weighting: {_e2!r}")
            else:
                st.caption("ℹ tree_weighting ВКЛ, но терминал недоступен (нет sl_money) — "
                           "объём пересчитается в main.py на боевой машине.")

        # ── Премия/дисконт по тактике входа (отчёт tactic_tilt.json с боевой машины) ──
        # main.py применяет тильт В САМОМ КОНЦЕ реранка, поэтому в active_state.json
        # объём уже С надбавкой. Здесь только показываем: какая пара её получила,
        # на каком окне (≤90 дн.) и сколько стратегий изменилось.
        df_plan['Тактика'] = '—'
        try:
            import tactic_tilt as _ttd
            _tilt = _ttd.load_tilt() or {}
            _applied = (_tilt.get('applied') or {})
            if _applied:
                _tsym = set(_applied.keys())
                df_plan['Тактика'] = [
                    (f"×{_applied[_s]['mult']:.2f} "
                     f"({'премия' if _applied[_s].get('side') == 'premium' else 'дисконт'})")
                    if _s in _tsym else '—' for _s in df_plan['symbol']
                ]
            _line = ''  # тильт в Daily Plan НЕ печатаем: он виден в лейблах Overview
            if _line:
                st.caption(f"Объём с надбавкой (окно {_tilt.get('window_days', 90)} дн., "
                           f"отчёт {str(_tilt.get('ts', '—')).replace('T', ' ')}): {_line}")
            elif False:  # причина тоже не нужна: тильт виден в лейблах Overview
                st.caption(f"Тильт не применён: {_tilt['reason']}")
            else:
                pass  # в Daily Plan ничего не печатаем (тильт — в лейблах Overview)
        except Exception as _te:
            st.caption(f"⚠ tactic_tilt: {_te!r}")

        # ── Шапка-сводка ──
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Стратегий в плане", len(df_plan))
        c2.metric("Planned volume", f"{df_plan['lot'].sum():.2f} lots")
        c3.metric("Risk budget", f"{_quota:,.0f} RUB")
        _used = df_plan['risk ₽'].dropna().sum()
        c4.metric("Used risk", f"{_used:,.0f} RUB" if _used > 0 else "—")

        # ── План ↔ Strategy Tree: тот же уровень гранулярности (категория symbol+family) ──
        # Tree считает PnL по реальным закрытым сделкам окна аллокации; план — по стратегиям.
        # Здесь сводим их вместе, чтобы было видно: куда реально идёт объём.
        # ── Гистограмма: Σ объём по КАТЕГОРИЯМ (символ + семейство) ──
        # Квота живёт на категории, поэтому и объём показываем категорией.
        # Разбивка по стратегиям — на графике ниже (там param_key уместен).
        if PLOTLY_AVAILABLE and not df_plan.empty:
            _cbar = (df_plan.groupby('sid')
                     .agg(lot=('lot', 'sum'), category=('category', 'first'),
                          pnl=('Tree PnL ₽', 'first'), n=('sid', 'size'))).reset_index()
            _cbar = _cbar[_cbar['lot'] > 0].sort_values('lot', ascending=True).reset_index(drop=True)
            if not _cbar.empty:
                _cbar['color'] = _cbar['pnl'].apply(
                    lambda v: '#DA3633' if (v is not None and v == v and v < 0) else '#2EA043')
                _cbar['pnl_txt'] = _cbar['pnl'].apply(
                    lambda v: (f"{v:,.0f}".replace(',', ' ') + ' ₽') if (v is not None and v == v) else '—')
                _cbar['hover'] = _cbar.apply(
                    lambda r: f"Tree PnL: {r['pnl_txt']} · стратегий: {r['n']}", axis=1)
                fig_cat = go.Figure(go.Bar(
                    x=_cbar['category'], y=_cbar['lot'], marker_color=_cbar['color'],
                    customdata=_cbar[['hover']].values,
                    hovertemplate='<b>%{x}</b><br>Σ объём: %{y:.2f} лот<br>'
                                  '%{customdata[0]}<extra></extra>'))
                plotly_dark_layout(fig_cat, height=560)
                fig_cat.update_xaxes(tickangle=-60)
                fig_cat.update_yaxes(title_text='Σ объём, лот')
                st.markdown("#### Объём по категориям (символ + семейство)")
                st.plotly_chart(fig_cat, use_container_width=True)
        st.markdown("#### План по категориям (символ + семейство)")
        _cat_rows = []
        for _sid, _grp in df_plan.groupby('sid'):
            _ccat = _cat_by_id.get(_sid, {})
            _cpnl = _ccat.get('pnl')
            _cvol = float(_ccat.get('volume') or 0.0)
            _ctr = _ccat.get('trades')
            _lot_sum = float(_grp['lot'].sum())
            _risk_sum = float(_grp['risk ₽'].dropna().sum()) if _grp['risk ₽'].notna().any() else None
            _cat_rows.append({
                'Категория': _grp['category'].iloc[0],
                'Tree PnL ₽': ('—' if _cpnl is None else f"{_cpnl:,.0f}".replace(',', ' ')),
                'Tree ₽/лот': (f"{_cpnl / _cvol:,.0f}".replace(',', ' ')
                               if (_cpnl is not None and _cvol) else '—'),
                'Tree trades': ('—' if _ctr is None else str(int(_ctr))),
                'Стратегий': len(_grp),
                'Σ lot': round(_lot_sum, 2),
                'Σ risk ₽': (round(_risk_sum, 0) if _risk_sum is not None else None),
                '_pnl': _cpnl,
                '_lot': _lot_sum,
            })
        if _cat_rows:
            _dfc = pd.DataFrame(_cat_rows)
            _tot_lot = float(_dfc['_lot'].sum())
            _green = float(_dfc.loc[_dfc['_pnl'] > 0, '_lot'].sum())
            _red = float(_dfc.loc[_dfc['_pnl'] < 0, '_lot'].sum())
            _na = float(_dfc.loc[_dfc['_pnl'].isna(), '_lot'].sum())

            def _share(_v, _tot=_tot_lot):
                return f"{100.0 * _v / _tot:.0f}%" if _tot > 0 else "—"

            # ── Перевес: кто кого перевешивает по прибыли и по объёму ──
            # Зелёные = категории с Tree PnL > 0, красные = PnL < 0.
            # Перевес по прибыли = сумма PnL зелёных + сумма PnL красных (красные уже < 0).
            # Перевес по объёму = доля объёма плана, стоящая в красных категориях.
            _pnl_g = float(_dfc.loc[_dfc['_pnl'] > 0, '_pnl'].sum())
            _pnl_r = float(_dfc.loc[_dfc['_pnl'] < 0, '_pnl'].sum())
            _n_g = int((_dfc['_pnl'] > 0).sum())
            _n_r = int((_dfc['_pnl'] < 0).sum())
            _bal = _pnl_g + _pnl_r
            _red_pct = (100.0 * _red / _tot_lot) if _tot_lot > 0 else None
            _g1, _g2, _g3 = st.columns(3)
            _g1.metric("Зелёные", f"{_pnl_g:+,.0f} ₽".replace(',', ' '),
                       delta=f"{_green:.2f} лот.", delta_color="off")
            _g1.caption(f"{_n_g} кат.")
            _g2.metric("Красные", f"{_pnl_r:+,.0f} ₽".replace(',', ' ').replace('-', '−'),
                       delta=f"{_red:.2f} лот.", delta_color="off")
            _g2.caption(f"{_n_r} кат.")
            _g3.metric("Перевес", f"{_bal:+,.0f} ₽".replace(',', ' ').replace('-', '−'),
                       delta=(f"{_red_pct:.0f}% объёма у красных" if _red_pct is not None
                              else None),
        
                       delta_color="off")
            _g3.caption("зелёные + красные")
            _mc1, _mc2, _mc3, _mc4 = st.columns(4)
            _mc1.metric("Категорий в плане", f"{len(_dfc)}")
            _mc2.metric("Объём в зелёных", _share(_green))
            _mc3.metric("Объём в красных", _share(_red))
            _mc4.metric("Объём без данных", _share(_na))
            _dfc['Флаг'] = [
                ('⚠ красная, а объём есть' if (pd.notna(_p) and _p < 0 and _l > 0.01)
                 else ('— нет сделок в окне' if pd.isna(_p) else ''))
                for _p, _l in zip(_dfc['_pnl'], _dfc['_lot'])]
            _covered = int(_dfc['Tree PnL ₽'].ne('—').sum())
            st.caption(f"Категорий с данными Tree: {_covered} из {len(_dfc)} · Σ объём плана: "
                       f"{_tot_lot:.2f} лот · категория = symbol+family — тот же уровень, что в "
                       f"Strategy Tree (окно {ALLOC_DAYS} дн.).")
            st.dataframe(_dfc.drop(columns=['_pnl', '_lot']).sort_values('Σ lot', ascending=False), key='plan_cat_big',
                         use_container_width=True, hide_index=True)


        # ── Гистограмма: план объёма по стратегиям ──
        if False:  # СКРЫТО (запрос): «План объёма по стратегиям (лот на стратегию)» убран из Daily Plan
            _bar = df_plan[df_plan['lot'] > 0].sort_values('lot', ascending=True).reset_index(drop=True)
            _bar['label'] = _bar.apply(lambda r: f"{r['category']} {r['param_key']}", axis=1)
            _bar['color'] = _bar['Tree PnL ₽'].apply(
                lambda v: '#DA3633' if (v is not None and v < 0) else '#2EA043')
            fig_bar = go.Figure(go.Bar(
                x=_bar['label'], y=_bar['lot'], marker_color=_bar['color'],
                customdata=_bar[['Tree PnL ₽', 'BT score']].values,
                hovertemplate='<b>%{x}</b><br>Объём: %{y:.2f} лот<br>'
                              'Tree PnL: %{customdata[0]:,.0f} ₽<br>'
                              'BT score: %{customdata[1]:.2f}<extra></extra>'))
                
            plotly_dark_layout(fig_bar, height=560)
            fig_bar.update_xaxes(tickangle=-60)
            fig_bar.update_yaxes(title_text='Объём, лот')
            st.markdown("#### План объёма по стратегиям (лот на стратегию)")
            st.plotly_chart(fig_bar, use_container_width=True)

            # ── Гистограмма С ПОПРАВКОЙ: объём по реальным сделкам ──
            if False:  # дубль графика убран
                _bar2 = df_plan.copy()
                _bar2['Lot (tree)'] = pd.to_numeric(_bar2['Lot (tree)'], errors='coerce').fillna(0.0)
                _bar2 = _bar2[_bar2['Lot (tree)'] > 0].copy()
                _bar2['label'] = _bar2.apply(lambda r: f"{r['category']} {r['param_key']}", axis=1)
                _bar2 = _bar2.sort_values('Lot (tree)', ascending=True).reset_index(drop=True)
                _c2 = _bar2['Tree PnL ₽'].apply(lambda v: '#DA3633' if (v is not None and v < 0) else '#2EA043')
                fig_bar2 = go.Figure(go.Bar(
                    x=_bar2['label'], y=_bar2['Lot (tree)'], marker_color=_c2,
                    customdata=_bar2[['Tree PnL ₽', 'lot']].values,
                    hovertemplate='<b>%{x}</b><br>Лот с поправкой: %{y:.2f}<br>'
                                  'Сейчас: %{customdata[1]:.2f} лот<br>'
                                  'Tree PnL: %{customdata[0]:,.0f} ₽<extra></extra>'))
                plotly_dark_layout(fig_bar2, height=560)
                fig_bar2.update_xaxes(tickangle=-60)
                fig_bar2.update_yaxes(title_text='Объём с поправкой, лот')
                st.markdown("#### План объёма С ПОПРАВКОЙ (Tree-weighted: красные → min_lot)")
                st.plotly_chart(fig_bar2, use_container_width=True)
            _unused_pie = """
            _pie = _pie[_pie['lots'] > 0].sort_values('lots', ascending=False)
            fig_pie = go.Figure(go.Pie(
                labels=_pie['category'], values=_pie['lots'], hole=0.45,
                textinfo='label+percent', textposition='outside',
                texttemplate='%{label}<br>%{value:.2f} лот (%{percent})'))
            plotly_dark_layout(fig_pie, height=460)
            st.markdown("#### План объёма по категориям (валюта + семейство)")
            """  # end disabled pie code

        # ── Полная таблица плана ──
        # СКРЫТО (запрос): «Полный план (по стратегиям)» убран из Daily Plan.
        _unused_full_plan = """
        st.markdown("#### Полный план (по стратегиям)")
        # Tree-метрика NaN = «нет сделок в окне аллокации» (не ноль!). В таблице — «—».
        _n_no_tree = int(df_plan['Tree PnL ₽'].isna().sum()) if 'Tree PnL ₽' in df_plan.columns else 0
        if _n_no_tree:
            st.caption(f"ℹ {_n_no_tree} из {len(df_plan)} стратегий — без закрытых сделок в окне "
                       f"{ALLOC_DAYS} дн.: Tree PnL / Tree ₽/лот / Tree trades не определены (—). "
                       f"Это не ноль: в _soft_weighted_lots такая категория получает нейтральный ×1.0.")
        _disp = df_plan.copy()
        for _c in ('Tree PnL ₽', 'Tree ₽/лот', 'Tree trades'):
            if _c in _disp.columns:
                _disp[_c] = _disp[_c].apply(
                    lambda v, _n=_c: '—' if (v is None or v != v)
                    else (str(int(v)) if _n == 'Tree trades' else f"{v:,.0f}".replace(',', ' ')))
        _cols = [c for c in ['symbol', 'family', 'param_key', 'category', 'SL', 'TP',
                             'lot', 'risk ₽', 'BT score', 'BT PF', 'BT WR %', 'BT trades',
                             'Tree PnL ₽', 'Tree ₽/лот', 'Tree trades',
                             'Q cur %', 'Q new %', 'flag'] if c in df_plan.columns]
        # Добавляем sid для отладки (показывает, что Tree PnL и квота — по категории)
        if 'sid' not in _cols:
            _cols.insert(4, 'sid')
        st.dataframe(
            _disp[_cols].sort_values('lot', ascending=False).reset_index(drop=True),
            use_container_width=True, hide_index=True,
            column_config={
                'lot': st.column_config.NumberColumn(format="%.2f"),
                # (Lot (tree) убран)
                'risk ₽': st.column_config.NumberColumn(format="%.0f"),
                'BT score': st.column_config.NumberColumn(format="%.2f"),
                'BT PF': st.column_config.NumberColumn(format="%.2f"),
                'Tree PnL ₽': st.column_config.TextColumn(),
                'Tree ₽/лот': st.column_config.TextColumn(),
                'Q cur %': st.column_config.NumberColumn(format="%.1f"),
                'Q new %': st.column_config.NumberColumn(format="%.1f"),
            })
        """  # СКРЫТО (запрос): «Полный план (по стратегиям)» убран из Daily Plan


with tab_risk:
    if not data:
        st.warning("No data.")
        st.stop()

    st.markdown("### Risk Utilization")
    quota = data['quota']
    positions = None

    if MT5_AVAILABLE:
        try:
            mt5.initialize()
            positions = mt5.positions_get()
        except Exception:
            positions = None

    if positions is not None and len(positions) > 0:
        unrealized_pnl = sum(p.profit for p in positions)
        total_volume = sum(p.volume for p in positions)
        n_positions = len(positions)

        max_loss = 0.0
        no_sl_count = 0
        risk_by_symbol = {}

        for p in positions:
            sl_loss = 0.0
            if p.sl != 0:
                info = mt5.symbol_info(p.symbol)
                if info and info.trade_tick_value > 0 and info.trade_tick_size > 0:
                    sl_distance = abs(p.price_current - p.sl)
                    loss_in_ticks = sl_distance / info.trade_tick_size
                    sl_loss = p.volume * loss_in_ticks * info.trade_tick_value
            else:
                no_sl_count += 1
            max_loss += sl_loss

            sym = p.symbol.replace('rfd', '')
            if sym not in risk_by_symbol:
                risk_by_symbol[sym] = {'count': 0, 'volume': 0.0, 'pnl': 0.0, 'max_loss': 0.0}
            risk_by_symbol[sym]['count'] += 1
            risk_by_symbol[sym]['volume'] += p.volume
            risk_by_symbol[sym]['pnl'] += p.profit
            risk_by_symbol[sym]['max_loss'] += sl_loss

        risk_pct = (max_loss / quota * 100) if quota > 0 else 0

        st.metric("Risk Budget", f"{quota:,.0f} RUB")

        # Среднее время удержания закрытой позиции за окно дашборда: open_time →
        # timestamp (обе метки — серверное время MT5). Позиции, открытые до начала
        # окна, отброшены: у них IN-сделки в выборке нет (open_time = NaT).
        hold_h = None
        hold_n = 0
        _tdf = data.get('trades_df')
        if _tdf is not None and 'open_time' in _tdf.columns and len(_tdf):
            _hold = (_tdf['timestamp'] - _tdf['open_time']).dt.total_seconds() / 3600.0
            _hold = _hold[_hold.notna() & (_hold >= 0)]
            if len(_hold):
                hold_h = float(_hold.mean())
                hold_n = int(len(_hold))

        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        with col_r1:
            # Счётчик позиций и суммарный объём одной метрикой: «51/0.50».
            st.metric("Open Positions / lot", f"{n_positions}/{total_volume:.2f}")
        with col_r2:
            st.metric("Unrealized P&L", f"{unrealized_pnl:+,.1f} RUB",
                      delta_color="inverse")
        with col_r3:
            st.metric("Max Risk (SL)", f"{max_loss:,.1f} RUB")
        with col_r4:
            # Удержание: часы, в скобках — дни; среднее по закрытым позициям окна.
            st.metric("Avg Hold, h (d)",
                      f"{hold_h:.1f} ({hold_h / 24:.1f})" if hold_h is not None else "—")

        # ── Gauge ──
        fig_gauge = go.Figure()
        fig_gauge.add_trace(go.Indicator(
            mode="gauge+number",
            value=risk_pct,
            number={'suffix': '%', 'font': {'size': 28, 'color': COL_TEXT}},
            gauge={
                'axis': {'range': [0, 150], 'tickwidth': 1,
                         'tickcolor': COL_MUTED,
                         'tickfont': dict(size=16, color=COL_MUTED)},
                'bar': {'color': COL_TEXT, 'thickness': 0.12},
                'steps': [
                    {'range': [0, 30], 'color': '#1A2E1F'},
                    {'range': [30, 70], 'color': '#2E2A1A'},
                    {'range': [70, 150], 'color': '#2E1A1A'},
                ],
            },
        ))
        fig_gauge.update_layout(
            paper_bgcolor=COL_PANEL, height=200,
            margin=dict(l=40, r=40, t=10, b=10),
            font=dict(color=COL_TEXT, family='SF Mono, Consolas, monospace'),
        )
        st.plotly_chart(fig_gauge, use_container_width=True, key="risk_gauge")

        # ── Risk by symbol ──
        if risk_by_symbol:
            df_risk = pd.DataFrame([
                {'symbol': s, **v} for s, v in risk_by_symbol.items()
            ]).sort_values('max_loss', ascending=True)
            risk_colors = make_gradient_colors([-x for x in df_risk['max_loss']])

            fig_risk = go.Figure()
            fig_risk.add_trace(go.Bar(
                x=df_risk['max_loss'], y=df_risk['symbol'],
                orientation='h', marker_color=risk_colors,
                text=df_risk['count'], textposition='outside',
                texttemplate='%{text}',
                hovertemplate='<b>%{y}</b><br>Risk: %{x:,.1f} RUB<br>Positions: %{text}<extra></extra>',
                name='',
            ))
            fig_risk.update_layout(
                xaxis_title='Max risk by SL (RUB)',
                bargap=0,
            )
            st.plotly_chart(plotly_dark_layout(fig_risk, max(200, len(df_risk) * 30 + 60)),
                           use_container_width=True, key="risk_by_symbol")

        caption = f"Open: {n_positions} | Volume: {total_volume:.2f} lots | Budget: {quota:,.0f} RUB"
        if hold_h is not None:
            # Размер выборки важен: среднее по 2 позициям ничего не значит.
            caption += f" | Avg hold: {hold_h:.1f} h over {hold_n} closed"
        if no_sl_count > 0:
            caption += f" | {no_sl_count} positions without SL"
        st.caption(caption)

    elif positions is not None and len(positions) == 0:
        st.metric("Risk Budget", f"{quota:,.0f} RUB")
        st.info("No open positions — risk is zero.")
    else:
        st.metric("Risk Budget", f"{quota:,.0f} RUB")
        if data.get('active_strategies'):
            active = [s for s in data['active_strategies'] if s.get('has_position')]
            n = len(active)
            total_lot = sum(s.get('lot', 0) for s in active)
            st.metric("Open Positions / lot (from strategies)", f"{n}/{total_lot:.2f}")
            # Объём объединён со счётчиком позиций выше («Open Positions / lot»).
            st.caption(f"MT5 unavailable for detailed risk | Budget: {quota:,.0f} RUB")
        else:
            st.info("No open positions.")





















































            



            









    # ── Exposure heatmap ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        st.markdown("### Exposure Matrix")
        df_heat = data['trades_df'].copy()

        if days_back <= 3:
            df_heat['bucket'] = df_heat['timestamp'].dt.floor('h')
            bucket_fmt = '%d.%m %H:%M'
        elif days_back <= 14:
            df_heat['bucket'] = df_heat['timestamp'].dt.floor('4h')
            bucket_fmt = '%d.%m %Hh'
        else:
            df_heat['bucket'] = df_heat['timestamp'].dt.floor('D')
            bucket_fmt = '%d.%m'

        pivot = df_heat.pivot_table(
            index='symbol', columns='bucket',
            values='profit_net', aggfunc='count', fill_value=0,
        )
        symbols_order = sorted(pivot.index)
        pivot = pivot.loc[symbols_order]
        display_symbols = [s.replace('rfd', '') for s in pivot.index]
        time_labels = [col.strftime(bucket_fmt) for col in pivot.columns]
        z_max = max(3, pivot.values.max())

        fig_heat = go.Figure(data=go.Heatmap(
            z=pivot.values, x=time_labels, y=display_symbols,
            colorscale=[
                [0.0, '#161B22'],
                [0.33, '#1A3A1F'],
                [0.66, '#3A3A1A'],
                [1.0, '#3A1A1F'],
            ],
            zmin=0, zmax=z_max,
            text=pivot.values, texttemplate='%{text}',
            textfont=dict(size=16, color=COL_TEXT),
            hovertemplate='Symbol: %{y}<br>Time: %{x}<br>Trades: %{z}<extra></extra>',
        ))
        fig_heat.update_layout(
            xaxis_title='Time', yaxis_title='Symbol',
            xaxis=dict(tickangle=-45),
        )
        st.plotly_chart(plotly_dark_layout(fig_heat, 320), use_container_width=True,
                       key="risk_exposure_heatmap")
        st.caption("Scale: 0 — dark, 1-2 — green, 3 (limit) — amber, >3 — red")

    # ── Realized P&L by currency ──
    # Источник — data['trades_df']: одна строка = одна ЗАКРЫТАЯ позиция окна дашборда,
    # profit_net — реализованный результат в валюте счёта (₽), уже с комиссией и свопом.
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        # ═══════════════════════════════════════════════════════════
        #  ЛУЧШАЯ ТАКТИКА ВХОДА (одна строка вместо развёрнутого разбора)
        # ═══════════════════════════════════════════════════════════
        # Пироги отвечают «сколько», но не «что делать». Здесь считаем:
        #  - какая валюта даёт лучший/худший результат НА СДЕЛКУ (₽/сд., а не
        #    абсолют — иначе крупный объём всегда «выигрывает»);
        #  - какой день ВЫХОДА лучший и — с учётом среднего времени удержания —
        #    в какой день надо ЗАХОДИТЬ: день входа = день выхода − холд в днях
        #    (выход в среду при холде 24 ч ⇒ заходить во вторник);
        #  - развёрнутый разбор (лучшая/худшая валюта, топ-3 связок, «избегать») убран по запросу.
        # ── ЛУЧШАЯ ТАКТИКА ВХОДА: одна строка + цифры подтверждения ──
        # Категория = валюта (символ без 'rfd') × день ВЫХОДА сделки. День входа =
        # день выхода − средний холд в днях (выход в среду при холде 24 ч ⇒ заходить
        # во вторник). Всё остальное (лучшая валюта, худший день и т.п.) убрано.
        _ins2 = data['trades_df'].copy()
        _ih2 = None
        if not _ins2.empty and 'timestamp' in _ins2.columns:
            _ins2['ccy'] = _ins2['symbol'].astype(str).str.replace('rfd', '')
            _ins2['wd'] = _ins2['timestamp'].dt.weekday
            _ins2 = _ins2[_ins2['wd'] < 5]  # суббота/воскресенье — не торговые дни
            # Окно тактик: вся история, но НЕ больше 90 дней — дальше это скользящее
            # окно (то же окно использует tactic_tilt.py для премии/дисконта в плане).
            _ins2 = _ins2[_ins2['timestamp'] >= (pd.Timestamp.now() - pd.Timedelta(days=90))]
            if 'open_time' in _ins2.columns:
                _h2 = (_ins2['timestamp'] - _ins2['open_time']).dt.total_seconds() / 3600.0
                _h2 = _h2[_h2.notna() & (_h2 >= 0)]
                if len(_h2):
                    _ih2 = float(_h2.mean())
        # Сдвиг назад по рабочим дням: 24 ч холда = 1 день.
        _shift2 = max(0, min(int(round((_ih2 or 0.0) / 24.0)), 4))
        # Средний холд ПО ВАЛЮТЕ, а не «в среднем по больнице»: у йены сделка может
        # жить 3 дня, у мажоров — сутки, и тогда день входа у них разный. Общий
        # средний холд остаётся только фолбэком, когда по валюте данных нет.
        _hold_ccy2 = {}
        if not _ins2.empty and 'ccy' in _ins2.columns and 'open_time' in _ins2.columns:
            _hd2 = _ins2.copy()
            _hd2['hold_h'] = (_hd2['timestamp'] - _hd2['open_time']).dt.total_seconds() / 3600.0
            _hd2 = _hd2[_hd2['hold_h'].notna() & (_hd2['hold_h'] >= 0)]
            if len(_hd2):
                _hold_ccy2 = {str(_k): float(_v) for _k, _v in
                              _hd2.groupby('ccy')['hold_h'].mean().items()}

        def _shift_for(_ccy):
            """Шаг назад в РАБОЧИХ днях по холду этой валюты (0..4).

            Рабочие дни, а не календарные: холд 24 ч с выходом в понедельник даёт
            вход в пятницу — выходные просто перепрыгиваются.
            """
            _h = _hold_ccy2.get(str(_ccy))
            if _h is None:
                _h = _ih2 or 0.0
            return max(0, min(int(round(float(_h) / 24.0)), 4))

        def _hold_txt(_ccy):
            """Холд для подписи: дни + часы, чтобы видно было, откуда взялся день входа."""
            _h = _hold_ccy2.get(str(_ccy))
            if _h is None:
                return "холд — нет данных (общий {:.1f} дн.)".format((_ih2 or 0.0) / 24.0)
            return f"холд {_h / 24.0:.1f} дн. ({_h:.0f} ч)"
        # Предлог уже внутри формы: «во вторник», «в среду» — иначе «в вторник».
        _WD2 = ('в понедельник', 'во вторник', 'в среду', 'в четверг', 'в пятницу')

        def _entry_idx2(_wd, _shift=None):
            _i = int(_wd)
            for _ in range(_shift2 if _shift is None else int(_shift)):
                _i = 4 if _i == 0 else _i - 1
            return _i

        # Два лейбла рядом: слева ЛУЧШАЯ связка, справа ХУДШАЯ — одна вёрстка,
        # разные концы одного и того же ранжирования по сумме PnL.
        # Надбавка/урезание объёма по тактике (tactic_tilt.py): ±pct из config.
        # Показываем её прямо в лейбле — отдельного блока в дэшборде нет.
        _tilt_pct = float(getattr(_SteeringParams, 'tactic_tilt_pct', 0.20)) * 100.0
        _col_best, _col_worst = st.columns(2)
        _col_best.markdown("### Лучшая тактика входа")
        _col_worst.markdown("### Худшая тактика входа")
        _cmb2 = pd.DataFrame()
        if not _ins2.empty and 'ccy' in _ins2.columns and 'wd' in _ins2.columns:
            _agg2 = {'pnl': ('profit_net', 'sum'), 'trades': ('profit_net', 'count')}
            if 'volume' in _ins2.columns:
                _agg2['lots'] = ('volume', 'sum')
            _cmb2 = _ins2.groupby(['ccy', 'wd']).agg(**_agg2).reset_index()
            if 'lots' not in _cmb2.columns:
                _cmb2['lots'] = 0.0
            _cmb2['per'] = _cmb2.apply(
                lambda _r: (_r['pnl'] / _r['trades']) if _r['trades'] else 0.0, axis=1)
            # Связка с 1 сделкой — шум, а не тактика: требуем >= 2.
            # Ранг — СУММА PnL связки, а не ₽/сд.: иначе маленькая, но «плотная»
            # связка (мало сделок, высокая удельная) перебивала бы крупную прибыль.
            _cmb2 = _cmb2[_cmb2['trades'] >= 2].sort_values('pnl', ascending=False)
        if _cmb2.empty:
            _col_best.caption("Пока нечего советовать: в окне меньше двух закрытых сделок на связку "
                              "«валюта + день недели».")
        else:
            _bb = _cmb2.iloc[0]
            _ccy_b, _wd_b = str(_bb['ccy']), int(_bb['wd'])
            _col_best.markdown(f"Входить по **{_ccy_b}** {_WD2[_entry_idx2(_wd_b, _shift_for(_ccy_b))]}, "
                               f"выход {_WD2[_wd_b]} · объём +{_tilt_pct:.0f}%")
            _conf = (f"{int(_bb['pnl']):+,} ₽ за {int(_bb['trades'])} сд. · "
                     f"{int(_bb['per']):+,} ₽/сд.")
            if float(_bb['lots']) > 0:
                _conf += f" · {float(_bb['lots']):.2f} лот"
            _conf += f" · {_hold_txt(_ccy_b)} · окно ≤90 дн."  # холд именно этой валюты
            _col_best.caption(_conf)  # цифры — мелким серым, чтобы не сливались с тактикой

        # ── ХУДШАЯ ТАКТИКА ВХОДА: тот же расчёт и та же вёрстка, только берём
        #    последнюю связку ранжирования (минимальная сумма PnL в окне).
        if _cmb2.empty:
            _col_worst.caption("Пока нечего советовать: в окне меньше двух закрытых сделок "
                               "на связку «валюта + день недели».")
        elif len(_cmb2) < 2:
            # Одна связка — «худшая» и «лучшая» были бы одной строкой: не врём.
            _col_worst.caption("Худшая не определена: в окне всего одна связка «валюта + день».")
        else:
            _ww = _cmb2.iloc[-1]
            _ccy_w, _wd_w = str(_ww['ccy']), int(_ww['wd'])
            _col_worst.markdown(f"Входить по **{_ccy_w}** {_WD2[_entry_idx2(_wd_w, _shift_for(_ccy_w))]}, "
                                f"выход {_WD2[_wd_w]} · объём −{_tilt_pct:.0f}%")
            _conf_w = (f"{int(_ww['pnl']):+,} ₽ за {int(_ww['trades'])} сд. · "
                       f"{int(_ww['per']):+,} ₽/сд.")
            if float(_ww['lots']) > 0:
                _conf_w += f" · {float(_ww['lots']):.2f} лот"
            _conf_w += f" · {_hold_txt(_ccy_w)} · окно ≤90 дн."  # тот же холд, но по своей валюте
            _col_worst.caption(_conf_w)
        _ins = data['trades_df'].copy()  # старый расчёт ниже жив, но его вывод заглушён
        if not _ins.empty and 'timestamp' in _ins.columns:
            _ins['ccy'] = _ins['symbol'].astype(str).str.replace('rfd', '')
            _ins['wd'] = _ins['timestamp'].dt.weekday
            _ins = _ins[_ins['wd'] < 5]  # суббота/воскресенье — не торговые дни
        if not _ins.empty:
            # Средний холд считаем СВОЙ: метрика Avg Hold выше существует только
            # когда в терминале есть открытые позиции, а вывод нужен всегда.
            _ih = None
            if 'open_time' in _ins.columns:
                _hh = (_ins['timestamp'] - _ins['open_time']).dt.total_seconds() / 3600.0
                _hh = _hh[_hh.notna() & (_hh >= 0)]
                if len(_hh):
                    _ih = float(_hh.mean())
            _shift = int(round(_ih / 24.0)) if _ih is not None else 0
            _shift = max(0, min(_shift, 4))
            _RUWD = ('понедельник', 'вторник', 'среда', 'четверг', 'пятница')

            def _entry_day(_wd_exit):
                """День ВХОДА по дню выхода: шагаем назад по рабочим дням на _shift."""
                _i = int(_wd_exit)
                for _ in range(_shift):
                    _i = 4 if _i == 0 else _i - 1
                return _RUWD[_i]

            def _summ(_by):
                _g = (_ins.groupby(_by)
                      .agg(pnl=('profit_net', 'sum'),
                           trades=('profit_net', 'count'),
                           lots=('volume', 'sum'))
                      .reset_index())
                _g['per'] = _g.apply(
                    lambda _r: (_r['pnl'] / _r['trades']) if _r['trades'] else 0.0, axis=1)
                return _g

            _ccy_g = _summ('ccy').sort_values('per', ascending=False)
            _wd_g = _summ('wd').sort_values('per', ascending=False)
            _cmb = _summ(['ccy', 'wd'])
            # Связки с 1 сделкой — шум, а не закономерность: требуем >= 2.
            _cmb_ok = _cmb[_cmb['trades'] >= 2].sort_values('per', ascending=False)

            pass  # старый дубль заголовка убран
            if _ih is not None:
                _ = (f"Средний холд {_ih:.1f} ч ({_ih / 24:.1f} дн.) → день входа = "
                           f"день выхода − {_shift} дн. Дни ниже — по ВЫХОДУ сделки.")
            else:
                _ = "Средний холд неизвестен (нет open_time) — дни указаны по выходу сделки."
            _bul = []
            if len(_ccy_g):
                _b1, _w1 = _ccy_g.iloc[0], _ccy_g.iloc[-1]
                _bul.append(f"**Валюта:** лучшая — {_b1['ccy']} ({int(_b1['per']):+,} ₽/сд. за "
                            f"{int(_b1['trades'])} сд.), худшая — {_w1['ccy']} "
                            f"({int(_w1['per']):+,} ₽/сд. за {int(_w1['trades'])} сд.)")
            if len(_wd_g):
                _b2, _w2 = _wd_g.iloc[0], _wd_g.iloc[-1]
                _bul.append(f"**День выхода:** лучший — {_RUWD[int(_b2['wd'])]} "
                            f"({int(_b2['per']):+,} ₽/сд.), худший — {_RUWD[int(_w2['wd'])]} "
                            f"({int(_w2['per']):+,} ₽/сд.) → заходить: "
                            f"**{_entry_day(_b2['wd'])}**")
            for _, _r in _cmb_ok.head(3).iterrows():
                _bul.append(f"**{_r['ccy']} · выход {_RUWD[int(_r['wd'])]}** — "
                            f"{int(_r['pnl']):+,} ₽ за {int(_r['trades'])} сд. "
                            f"({int(_r['per']):+,} ₽/сд.) → заходить: **{_entry_day(_r['wd'])}**")
            if len(_cmb_ok) > 3:
                _tw = _cmb_ok.iloc[-1]
                _bul.append(f"**Избегать:** {_tw['ccy']} · выход {_RUWD[int(_tw['wd'])]} — "
                            f"{int(_tw['pnl']):+,} ₽ за {int(_tw['trades'])} сд. "
                            f"({int(_tw['per']):+,} ₽/сд.)")
            for _b3 in []:  # старые пункты убраны по запросу (осталась одна строка-тактика)
                st.markdown("- " + _b3)

        # Небольшой отступ сверху: блок тактики и заголовок пирогов визуально слипались.
        st.markdown("<div style='height:0.9rem;'></div>", unsafe_allow_html=True)
        st.markdown("### Currency Breakdown — realized P&L & volume")
        _ccy = data['trades_df'].copy()
        _ccy['ccy'] = _ccy['symbol'].str.replace('rfd', '')
        _ccy = _ccy.groupby('ccy').agg(
            pnl=('profit_net', 'sum'),
            trades=('profit_net', 'count'),
        ).reset_index()
        # Крупные куски — первыми, независимо от знака.
        _ccy = _ccy.sort_values('pnl', key=lambda s: s.abs(),
                                ascending=False).reset_index(drop=True)
        # База процентов — сумма МОДУЛЕЙ: плюс и минус по разным валютам не должны
        # гасить друг друга (иначе доля теряет смысл, а при нулевом итоге — мусор).
        _abs_total = float(_ccy['pnl'].abs().sum())
        # Два пирога рядом: реализованный P&L (₽) и оборот (лоты) по валютам.
        _col_pnl, _col_lots = st.columns(2)
        _col_pnl.markdown("#### Realized P&L, ₽")
        _labels, _values, _colors, _hover = [], [], [], []
        for _, _r in _ccy.iterrows():
            _pnl = float(_r['pnl'])
            _share = (abs(_pnl) / _abs_total * 100.0) if _abs_total > 0 else 0.0
            _labels.append(f"{_r['ccy']}: {_pnl:+,.0f} ₽ ({_share:.0f}%)")
            _values.append(abs(_pnl))
            _colors.append(COL_GREEN if _pnl >= 0 else COL_RED)
            _hover.append(f"<b>{_r['ccy']}</b><br>Realized: {_pnl:+,.0f} ₽<br>"
                          f"Share of Σ|P&L|: {_share:.1f}%<br>"
                          f"Closed positions: {int(_r['trades'])}")
        if _values and sum(_values) > 0:
            _fig_ccy = go.Figure(go.Pie(
                labels=_labels, values=_values, hole=0.45,
                marker=dict(colors=_colors, line=dict(color=COL_PANEL, width=2)),
                text=_labels, textinfo='text', textposition='outside',
                textfont=dict(size=14, color=COL_TEXT),
                customdata=_hover, hovertemplate='%{customdata}<extra></extra>',
                sort=False, showlegend=False,
            ))
            _col_pnl.plotly_chart(plotly_dark_layout(_fig_ccy, 480), use_container_width=True,
                                  key="risk_pnl_by_currency")
            _col_pnl.caption(f"Realized P&L of closed positions in window | % base = Σ|P&L| = "
                               f"{_abs_total:,.0f} ₽ (+ and − do not cancel) | slice = |P&L|")
        else:
            _col_pnl.info("No closed positions with non-zero P&L in the window.")

        # ── Пирог по обороту (лоты) — рядом с P&L ──
        # Тот же набор: ЗАКРЫТЫЕ позиции окна. volume — объём входа позиции (лоты),
        # т.е. сумма по валюте = «отработанный» оборот, а не текущая экспозиция.
        _col_lots.markdown("#### Volume, lots")
        _lots = data['trades_df'].copy()
        _lots['ccy'] = _lots['symbol'].str.replace('rfd', '')
        _lots = _lots.groupby('ccy').agg(
            lots=('volume', 'sum'),
            trades=('profit_net', 'count'),
        ).reset_index()
        _lots = _lots[_lots['lots'] > 0].sort_values(
            'lots', ascending=False).reset_index(drop=True)
        _lots_total = float(_lots['lots'].sum())
        _l_labels, _l_values, _l_hover = [], [], []
        for _, _r in _lots.iterrows():
            _v = float(_r['lots'])
            _sh = (_v / _lots_total * 100.0) if _lots_total > 0 else 0.0
            _l_labels.append(f"{_r['ccy']}: {_v:.2f} lots ({_sh:.0f}%)")
            _l_values.append(_v)
            _l_hover.append(f"<b>{_r['ccy']}</b><br>Volume: {_v:.2f} lots<br>"
                            f"Share: {_sh:.1f}%<br>Closed positions: {int(_r['trades'])}")
        if _l_values and _lots_total > 0:
            _fig_lots = go.Figure(go.Pie(
                labels=_l_labels, values=_l_values, hole=0.45,
                marker=dict(colors=[COL_BLUE] * len(_l_values),
                            line=dict(color=COL_PANEL, width=2)),
                text=_l_labels, textinfo='text', textposition='outside',
                textfont=dict(size=14, color=COL_TEXT),
                customdata=_l_hover, hovertemplate='%{customdata}<extra></extra>',
                sort=False, showlegend=False,
            ))
            _col_lots.plotly_chart(plotly_dark_layout(_fig_lots, 480),
                                   use_container_width=True,
                                   key="risk_volume_by_currency")
            _col_lots.caption(f"Volume of closed positions in window | "
                              f"total {_lots_total:.2f} lots")
        else:
            _col_lots.info("No closed volume in the window.")

        # ── То же по дням недели (день считается по времени ВЫХОДА сделки,
        # серверное время MT5 — как и везде в этом окне) ──
        st.markdown("### Weekday Breakdown — realized P&L & volume")
        _wd_names = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
        _wd = data['trades_df'].copy()
        _wd['wd'] = _wd['timestamp'].dt.weekday
        _wd = _wd.groupby('wd').agg(
            pnl=('profit_net', 'sum'),
            lots=('volume', 'sum'),
            trades=('profit_net', 'count'),
        ).reset_index().sort_values('wd').reset_index(drop=True)
        _wd_abs = float(_wd['pnl'].abs().sum())
        _wd_lots_total = float(_wd['lots'].sum())
        _col_wd_pnl, _col_wd_lots = st.columns(2)
        _col_wd_pnl.markdown("#### Realized P&L by weekday, ₽")
        _col_wd_lots.markdown("#### Volume by weekday, lots")
        _w_labels, _w_values, _w_colors, _w_hover = [], [], [], []
        _wl_labels, _wl_values, _wl_hover = [], [], []
        for _, _r in _wd.iterrows():
            _nm = _wd_names[int(_r['wd'])]
            _pnl = float(_r['pnl'])
            _lots = float(_r['lots'])
            _sh = (abs(_pnl) / _wd_abs * 100.0) if _wd_abs > 0 else 0.0
            _shl = (_lots / _wd_lots_total * 100.0) if _wd_lots_total > 0 else 0.0
            _w_labels.append(f"{_nm}: {_pnl:+,.0f} ₽ ({_sh:.0f}%)")
            _w_values.append(abs(_pnl))
            _w_colors.append(COL_GREEN if _pnl >= 0 else COL_RED)
            _w_hover.append(f"<b>{_nm}</b><br>Realized: {_pnl:+,.0f} ₽<br>"
                            f"Share of Σ|P&L|: {_sh:.1f}%<br>Closed: {int(_r['trades'])}")
            _wl_labels.append(f"{_nm}: {_lots:.2f} lots ({_shl:.0f}%)")
            _wl_values.append(_lots)
            _wl_hover.append(f"<b>{_nm}</b><br>Volume: {_lots:.2f} lots<br>"
                             f"Share: {_shl:.1f}%<br>Closed: {int(_r['trades'])}")
        if _w_values and _wd_abs > 0:
            _fig_wd = go.Figure(go.Pie(
                labels=_w_labels, values=_w_values, hole=0.45,
                marker=dict(colors=_w_colors, line=dict(color=COL_PANEL, width=2)),
                text=_w_labels, textinfo='text', textposition='outside',
                textfont=dict(size=14, color=COL_TEXT),
                customdata=_w_hover, hovertemplate='%{customdata}<extra></extra>',
                sort=False, showlegend=False,
            ))
            _col_wd_pnl.plotly_chart(plotly_dark_layout(_fig_wd, 480),
                                     use_container_width=True,
                                     key="risk_pnl_by_weekday")
            _col_wd_pnl.caption(f"Closed positions by exit day | % base = Σ|P&L| = "
                                f"{_wd_abs:,.0f} ₽ (+ and − do not cancel)")
        else:
            _col_wd_pnl.info("No closed positions in the window.")
        if _wl_values and _wd_lots_total > 0:
            _fig_wdl = go.Figure(go.Pie(
                labels=_wl_labels, values=_wl_values, hole=0.45,
                marker=dict(colors=[COL_BLUE] * len(_wl_values),
                            line=dict(color=COL_PANEL, width=2)),
                text=_wl_labels, textinfo='text', textposition='outside',
                textfont=dict(size=14, color=COL_TEXT),
                customdata=_wl_hover, hovertemplate='%{customdata}<extra></extra>',
                sort=False, showlegend=False,
            ))
            _col_wd_lots.plotly_chart(plotly_dark_layout(_fig_wdl, 480),
                                      use_container_width=True,
                                      key="risk_volume_by_weekday")
            _col_wd_lots.caption(f"Volume of closed positions | total {_wd_lots_total:.2f} lots")
        else:
            _col_wd_lots.info("No closed volume in the window.")


# ═══════════════════════════════════════════════════════════════
    # ── ПИК нереализованной прибыли за день (trades_db.position_peak, ПО СДЕЛКЕ) ──
    # Сделка внутри дня проходит 99 → 101 → 140 → 200 ₽, а закрывается по 170.
    # На графике должна стоять точка 200 — максимум floating, который сэмплер
    # засёк за день, а НЕ результат закрытия. position_peak хранит по строке на
    # (день, position_id): peak_float / peak_per_lot — лучшая зафиксированная
    # точка ОДНОЙ сделки дня. На график берём ЛУЧШУЮ сделку каждого дня.
    _pkdf = data.get('pos_peaks_df')
    if not PLOTLY_AVAILABLE:
        pass
    elif _pkdf is None or getattr(_pkdf, 'empty', True):
        st.info("В trades_db.position_peak нет строк за окно. Пики пишет сэмплер main.py "
                "(EQUITY_SAMPLE_INTERVAL_SEC = 300 с); если процесс не работал в этот "
                "период — показывать нечего.")
    else:
        _pkdf = _pkdf.copy()
        for _c in ('peak_float', 'peak_per_lot', 'volume'):
            _pkdf[_c] = (pd.to_numeric(_pkdf[_c], errors='coerce')
                         if _c in _pkdf.columns else 0.0)
        _pkdf = _pkdf.dropna(subset=['peak_float', 'peak_per_lot'])
        if _pkdf.empty:
            st.info("В position_peak нет валидных значений (peak_float / peak_per_lot).")
        else:
            _ts_col = 'peak_ts'
            for _cand in ('peak_time', 'peak_ts'):
                if _cand in _pkdf.columns:
                    _ts_col = _cand
                    break
            _pkdf['_ts_s'] = (pd.to_datetime(_pkdf[_ts_col], errors='coerce')
                              .dt.strftime('%d.%m %H:%M').fillna(''))
            _pkdf['_vol'] = _pkdf['volume'].fillna(0.0)
            # тикет — строкой: в customdata он попадает вместе со строками (hover без «e+09»)
            if 'position_id' in _pkdf.columns:
                _pkdf['position_id'] = _pkdf['position_id'].astype(str)
            # Точки графиков считаются ТАК ЖЕ, как в спеке: см. ниже.
            # Удельная величина — по спеке: PnL / объём ЭТОЙ ЖЕ сделки (строки дня),
            # абсолютная — PnL этой же строки. На день ровно одна точка в каждом
            # графике, поэтому обе кривые описывают одни и те же события.
            # peak_per_lot уже = peak_float / volume этой же сделки (строки дня).

            # ОДНА строка на день для ОБОИХ графиков — события общие, поэтому и
            # траектории совпадают: берём СДЕЛКУ с максимальным пиком прибыли дня
            # (peak_float), а слева показываем ту же точку в ₽/лот.
            _pk_pl = (_pkdf.loc[_pkdf.groupby('day')['peak_float'].idxmax()]
                      .sort_values('day').reset_index(drop=True))
            # Удельная величина = тот же пик прибыли / объём этой же сделки
            _per_lot_day = _pk_pl['peak_per_lot']
            _pk_abs = (_pk_pl  # те же события дня: слева в ₽/лот, справа в ₽
                       .sort_values('day').reset_index(drop=True))

            def _pk_xlab(_frame):
                _days = list(pd.to_datetime(_frame['day']).dt.date)
                return [f"{_RU_MONTHS[_d.month - 1][:3]} {_d.day}" for _d in _days]

            _hov = ('<b>%{x}</b><br>%{customdata[0]} (#%{customdata[1]})<br>'
                    'пик зафиксирован: %{customdata[2]}<br>'
                    'объём сделки: %{customdata[3]:.2f} лот<br>')

            _fig_pkpl = go.Figure()
            _fig_pkpl.add_trace(go.Scatter(
                x=_pk_xlab(_pk_pl), y=_per_lot_day, mode='lines+markers',
                line=dict(color=COL_BLUE, width=2), marker=dict(size=6, color=COL_BLUE),
                customdata=_pk_pl[['category', 'position_id', '_ts_s', '_vol',
                                   'peak_float']].values,
                hovertemplate=(_hov + 'пик ₽/лот: %{y:,.0f}<br>'
                               'пик прибыли: %{customdata[4]:,.0f} ₽<extra></extra>'),
                name='макс ₽/лот за день'))
            _peak_pl = float(_per_lot_day.max())
            _lvl_pl = _peak_pl * 0.75
            _fig_pkpl.add_hline(y=_lvl_pl, line_dash='dash', line_color=COL_GREEN_LT,
                                annotation_text=(f"75% от пика {_peak_pl:,.0f} = {_lvl_pl:,.0f} ₽/лот".replace(',', ' ')),
                                annotation_position='top left')
            _fig_pkpl.add_hline(y=0, line_color=COL_MUTED, line_width=1)
            _fig_pkpl.update_layout(xaxis_title='', yaxis_title='₽ на лот (пик дня)')

            _fig_pkabs = go.Figure()
            _fig_pkabs.add_trace(go.Scatter(
                x=_pk_xlab(_pk_abs), y=_pk_abs['peak_float'], mode='lines+markers',
                line=dict(color=COL_AMBER, width=2), marker=dict(size=6, color=COL_AMBER),
                customdata=_pk_abs[['category', 'position_id', '_ts_s', '_vol',
                                    'peak_per_lot']].values,
                hovertemplate=(_hov + 'пик прибыли: %{y:,.0f} ₽<br>'
                               'удельно в пике: %{customdata[4]:,.0f} ₽/лот<extra></extra>'),
                name='макс прибыль за день, ₽'))
            _peak_abs = float(_pk_abs['peak_float'].max())
            _lvl_abs = _peak_abs * 0.75
            _fig_pkabs.add_hline(y=_lvl_abs, line_dash='dash', line_color=COL_GREEN_LT,
                                 annotation_text=(f"75% от пика {_peak_abs:,.0f} = {_lvl_abs:,.0f} ₽".replace(',', ' ')),
                                 annotation_position='top left')
            _fig_pkabs.add_hline(y=0, line_color=COL_MUTED, line_width=1)
            _fig_pkabs.update_layout(xaxis_title='', yaxis_title='₽ (пик дня)')

            _col_pl, _col_abs = st.columns(2)
            with _col_pl:
                st.markdown("### Максимум нереализованной прибыли за день (₽/лот, по сделке)")
                st.plotly_chart(plotly_dark_layout(_fig_pkpl, 380),
                                use_container_width=True, key="risk_peak_per_lot_day")
                _rec_pl = _pk_pl.loc[_per_lot_day.idxmax()]
                st.caption(
                    "Точка = МАКСИМУМ floating-прибыли на лот по ОДНОЙ сделке (позиции), "
                    "засечённый за день; "
                    "(та же сделка, что и на правом графике). Шаг сэмплера 5 мин — "
                    "фактический внутриминутный пик мог быть выше. Нереализованная прибыль — "
                    "не деньги на счету: позиция могла закрыться хуже пика. Рекорд окна: "
                    + f"{_peak_pl:,.0f} ₽/лот — {_rec_pl['category']} "
                      f"#{int(_rec_pl['position_id'])}, "
                      f"{_rec_pl['_ts_s']}, объём {_rec_pl['_vol']:.2f} лот.")
            with _col_abs:
                st.markdown("### Максимум нереализованной прибыли за день, ₽ (по сделке)")
                st.plotly_chart(plotly_dark_layout(_fig_pkabs, 380),
                                use_container_width=True, key="risk_peak_float_day")
                _rec_abs = _pk_abs.loc[_pk_abs['peak_float'].idxmax()]
                st.caption(
                    "Точка = МАКСИМУМ нереализованной (floating) прибыли в рублях по ОДНОЙ "
                    "сделке (позиции), засечённый внутри дня. Не PnL дня и не "
                    "результат закрытия. Шаг сэмплера 5 мин. Рекорд окна: "
                    + f"{_rec_abs['peak_float']:,.0f} ₽ — {_rec_abs['category']} "
                      f"#{int(_rec_abs['position_id'])}, "
                      f"{_rec_abs['_ts_s']}, объём {_rec_abs['_vol']:.2f} лот.")

if False:  # ── LEGACY: графики по закрытым сделкам (отключено, удалить при чистке) ──
    # Для каждого дня берём ЛУЧШУЮ закрытую сделку по ₽/лот (net PnL / объём):
    # «сколько максимум выжималось из одного лота за день». Пунктир — 75% от пика окна.
    if PLOTLY_AVAILABLE and data.get('trades_df') is not None and not data['trades_df'].empty:
        _tb = data['trades_df'].copy()
        _pnl_col = ('profit_net' if 'profit_net' in _tb.columns
                    else ('profit' if 'profit' in _tb.columns else None))
        if _pnl_col and 'volume' in _tb.columns and 'timestamp' in _tb.columns:
            _tb = _tb[pd.to_numeric(_tb['volume'], errors='coerce').fillna(0) > 0].copy()
            _tb['_per_lot'] = (pd.to_numeric(_tb[_pnl_col], errors='coerce')
                               / pd.to_numeric(_tb['volume'], errors='coerce'))
            _tb = _tb.dropna(subset=['_per_lot'])
            if not _tb.empty:
                _tb['_day'] = pd.to_datetime(_tb['timestamp']).dt.date
                _best = _tb.loc[_tb.groupby('_day')['_per_lot'].idxmax()].sort_values('_day')
                _xlab = [f"{_RU_MONTHS[_d.month - 1][:3]} {_d.day}" for _d in _best['_day']]
                _peak = float(_best['_per_lot'].max())
                _lvl75 = _peak * 0.75
                _fig_bpl = go.Figure()
                _fig_bpl.add_trace(go.Scatter(
                    x=_xlab, y=_best['_per_lot'], mode='lines+markers',
                    line=dict(color=COL_BLUE, width=2),
                    marker=dict(size=6, color=COL_BLUE),
                    customdata=(_best[['symbol']].values if 'symbol' in _best.columns
                                else [['']] * len(_best)),
                    hovertemplate='%{x}<br>макс ₽/лот: %{y:,.0f}<br>%{customdata[0]}<extra></extra>',
                    name='макс ₽/лот за день'))
                if _peak > 0:
                    _fig_bpl.add_hline(
                        y=_lvl75, line_dash='dash', line_color=COL_GREEN_LT,
                        annotation_text=f"75% от пика: {_lvl75:,.0f} ₽/лот".replace(',', ' '),
                        annotation_position='top left')
                _fig_bpl.add_hline(y=0, line_color=COL_MUTED, line_width=1)
                _fig_bpl.update_layout(xaxis_title='', yaxis_title='₽ на лот (максимум дня)')
                if False: st.markdown("### Максимум удельной прибыли за день (₽/лот)")  # заголовок — в колонке ниже (два графика в ряд)
                if False: st.plotly_chart(plotly_dark_layout(_fig_bpl, 380),
                                use_container_width=True, key="risk_best_per_lot")
                if False: st.caption("Точка = лучшая сделка дня по ₽ на лот (net PnL / объём). "
                           "Пунктир — 75% от пика за окно. Только закрытые сделки, "
                           "окно — как у остальных блоков Risk.")
                # ── То же в АБСОЛЮТЕ: лучшая сделка дня в рублях ──
                # Тот же отбор (лучшая сделка дня), но по абсолютному net PnL, без деления
                # на объём: «сколько денег принесла лучшая сделка дня». Удельный график
                # выше не меняется — это отдельная пара, а не замена.
                _best_abs = _tb.loc[_tb.groupby('_day')[_pnl_col].idxmax()].sort_values('_day')
                _peak_abs = float(_best_abs[_pnl_col].max())
                _lvl75_abs = _peak_abs * 0.75
                _fig_bpn = go.Figure()
                _fig_bpn.add_trace(go.Scatter(
                    x=_xlab, y=_best_abs[_pnl_col], mode='lines+markers',
                    line=dict(color=COL_AMBER, width=2),
                    marker=dict(size=6, color=COL_AMBER),
                    customdata=(_best_abs[['symbol']].values if 'symbol' in _best_abs.columns
                                else [['']] * len(_best_abs)),
                    hovertemplate='%{x}<br>макс прибыль: %{y:,.0f} ₽'
                                  '<br>%{customdata[0]}<extra></extra>',
                    name='макс прибыль за день, ₽'))
                if _peak_abs > 0:
                    _fig_bpn.add_hline(
                        y=_lvl75_abs, line_dash='dash', line_color=COL_GREEN_LT,
                        annotation_text=f"75% от пика: {_lvl75_abs:,.0f} ₽".replace(',', ' '),
                        annotation_position='top left')
                _fig_bpn.add_hline(y=0, line_color=COL_MUTED, line_width=1)
                _fig_bpn.update_layout(xaxis_title='', yaxis_title='₽ (лучшая сделка дня)')
                if False: st.markdown("### Максимум прибыли за день в рублях")  # заголовок — в колонке ниже
                # ══ Ряд 1: два графика на одной линии (₽/лот и ₽) ══
                # Фигуры уже собраны выше (_fig_bpl, _fig_bpn) — здесь только
                # выкладываем их в колонки, чтобы сравнивать «удельно/абсолютно»
                # на одном уровне глаз и по одним и тем же датам на оси X.
                _col_pl, _col_abs = st.columns(2)
                with _col_pl:
                    st.markdown("### Максимум удельной прибыли за день (₽/лот)")
                    st.plotly_chart(plotly_dark_layout(_fig_bpl, 380),
                                    use_container_width=True, key="risk_best_per_lot")
                    st.caption("Лучшая ЗАКРЫТАЯ сделка дня по ₽ на лот (net PnL / объём). "
                               "Пунктир — 75% от пика окна.")
                with _col_abs:
                    st.markdown("### Максимум прибыли за день, ₽")
                    st.plotly_chart(plotly_dark_layout(_fig_bpn, 380),
                                    use_container_width=True, key="risk_best_pnl_day")
                    st.caption("Лучшая ЗАКРЫТАЯ сделка дня по абсолютному net PnL. "
                               "Пунктир — 75% от пика окна.")

                # ══ Ряд 2: лучший ЗАФИКСИРОВАННЫЙ пик за день (trades_db.daily_peak) ══
                # Не «лучшая закрытая сделка», а максимум нереализованного floating,
                # который сэмплер main.py (300 с) успел записать за день. Строка
                # daily_peak = (день, категория symbol+family); на графике берём
                # ЛУЧШУЮ категорию дня — она и есть «лучший пик по сделкам дня».
                _pkdf = None  # ряд 2 (пики daily_peak) выключен: оставлены только два графика
                if False: st.markdown("### Лучший зафиксированный пик за день (нереализованная прибыль)")  # ВЫКЛ: лишний третий график, оставлены только два в ряду
                if _pkdf is None or getattr(_pkdf, 'empty', True):
                    0 and st.caption("В daily_peak нет строк за окно. Таблицу наполняет сэмплер "
                               "main.py (EQUITY_SAMPLE_INTERVAL_SEC = 300 с): если процесс "
                               "не работал в этот период или окно пустое — показывать нечего.")
                else:
                    _pk = (_pkdf.loc[_pkdf.groupby('day')['peak_float'].idxmax()]
                           .sort_values('day').reset_index(drop=True))
                    _pk_days = list(pd.to_datetime(_pk['day']).dt.date)
                    _pk_lab = [f"{_RU_MONTHS[_d.month - 1][:3]} {_d.day}" for _d in _pk_days]
                    _fig_pk = go.Figure(go.Bar(
                        x=_pk_lab, y=_pk['peak_float'],
                        marker_color=[COL_GREEN_LT if _v >= 0 else COL_RED_LT
                                      for _v in _pk['peak_float']],
                        customdata=_pk[['category', 'peak_time',
                                        'peak_volume', 'peak_per_lot']].values,
                        hovertemplate=('<b>%{x}</b><br>пик floating: %{y:,.0f} ₽<br>'
                                       '%{customdata[0]}<br>зафиксирован: %{customdata[1]}<br>'
                                       'объём: %{customdata[2]:.2f} лот · '
                                       '%{customdata[3]:,.0f} ₽/лот<extra></extra>'),
                        name='пик floating за день'))
                    _fig_pk.add_hline(y=0, line_color=COL_MUTED, line_width=1)
                    _fig_pk.update_layout(yaxis_title='₽ (пик категории за день)')
                    if False: st.plotly_chart(plotly_dark_layout(_fig_pk, 340),
                                    use_container_width=True, key="risk_peak_float_day")
                    _bpk = _pk.loc[_pk['peak_float'].idxmax()]
                    st.caption(
                        ("Столбик = МАКСИМАЛЬНЫЙ пик нереализованной прибыли, зафиксированный "
                         "сэмплером за день, по категории «символ+семейство» (лучшая категория дня). "
                         "Рекорд окна: {v:,.0f} ₽ — {cat}, {ts}, объём {vol:.2f} лот "
                         "({pl:,.0f} ₽/лот). Шаг сэмплера 5 мин, поэтому фактический экстремум "
                         "между замерами может быть выше. Нереализованная прибыль — не деньги "
                         "на счету: позиции могли закрыться хуже пика.").format(
                            v=float(_bpk['peak_float']), cat=_bpk['category'],
                            ts=pd.to_datetime(_bpk['peak_time']).strftime('%d.%m %H:%M'),
                            vol=float(_bpk['peak_volume'] or 0.0),
                            pl=float(_bpk['peak_per_lot'] or 0.0)))
                _unused_kw = dict(
                                use_container_width=True, key="risk_best_pnl_day")
                if False: st.caption("Точка = лучшая сделка дня по абсолютному net PnL (₽). "
                           "Пунктир — 75% от пика за окно. Только закрытые сделки, "
                           "окно — как у остальных блоков Risk.")


# ═══════════════════════════════════════════════════════════════
#  STRATEGIES
# ═══════════════════════════════════════════════════════════════
with tab_strategies:
    if not data:
        st.warning("No data.")
        st.stop()

    # ── P&L by strategy ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        st.markdown("### P&L by Strategy")
        df_strat = data['trades_df'].groupby(
            ['symbol', 'strategy_type', 'param_key']
        ).agg(pnl=('profit_net', 'sum'), trades=('profit_net', 'count')).reset_index()
        df_strat['name'] = (
            df_strat['symbol'].str.replace('rfd', '') + ' | ' +
            df_strat['strategy_type'] + ' | ' + df_strat['param_key']
        )
        df_strat = df_strat.sort_values('pnl', ascending=True).reset_index(drop=True)
        colors_strat = make_gradient_colors(df_strat['pnl'].tolist())

        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=df_strat['pnl'], y=df_strat['name'],
            orientation='h', marker_color=colors_strat,
            text=df_strat['trades'], textposition='outside',
            texttemplate='%{text}',
            hovertemplate='<b>%{y}</b><br>PnL: %{x:,.1f}<br>Trades: %{text}<extra></extra>',
            name='',
        ))
        fig1.update_layout(xaxis_title='P&L (RUB)', bargap=0.12)
        st.plotly_chart(plotly_dark_layout(fig1, max(450, len(df_strat) * 24)),
                       use_container_width=True, key="strat_pnl_bar")

    # ── Win Rate + Profit Factor ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        st.markdown("### Win Rate & Profit Factor by Family")
        df_wf = data['trades_df'].groupby('strategy_type').agg(
            wins=('profit_net', lambda x: (x > 0).sum()),
            losses=('profit_net', lambda x: (x < 0).sum()),
            gross_profit=('profit_net', lambda x: x[x > 0].sum()),
            gross_loss=('profit_net', lambda x: abs(x[x < 0].sum())),
            total=('profit_net', 'count'),
        ).reset_index()
        df_wf['win_rate'] = df_wf['wins'] / df_wf['total'] * 100
        df_wf['profit_factor'] = df_wf.apply(
            lambda r: r['gross_profit'] / r['gross_loss']
            if r['gross_loss'] > 0 else float('inf'), axis=1,
        )

        col_wr, col_pf = st.columns(2)
        with col_wr:
            df_wr_sorted = df_wf.sort_values('win_rate', ascending=True)
            wr_colors = make_gradient_colors(df_wr_sorted['win_rate'].tolist())
            fig_wr = go.Figure()
            fig_wr.add_trace(go.Bar(
                x=df_wr_sorted['win_rate'], y=df_wr_sorted['strategy_type'],
                orientation='h', marker_color=wr_colors,
                text=df_wr_sorted['win_rate'].round(1),
                texttemplate='%{text}%', textposition='outside',
                hovertemplate='<b>%{y}</b><br>WR: %{text}%<extra></extra>',
                name='',
            ))
            fig_wr.update_layout(xaxis_title='Win Rate (%)', bargap=0.15)
            st.plotly_chart(plotly_dark_layout(fig_wr, max(250, len(df_wr_sorted) * 30 + 40)),
                           use_container_width=True, key="strat_winrate_bar")

        with col_pf:
            df_pf_sorted = df_wf.sort_values('profit_factor', ascending=True)
            df_pf_sorted['profit_factor'] = df_pf_sorted['profit_factor'].replace(
                [float('inf'), -float('inf')], 3.0
            )
            pf_colors = make_gradient_colors(df_pf_sorted['profit_factor'].tolist())
            fig_pf = go.Figure()
            fig_pf.add_trace(go.Bar(
                x=df_pf_sorted['strategy_type'], y=df_pf_sorted['profit_factor'],
                marker_color=pf_colors,
                text=df_pf_sorted['profit_factor'].round(2),
                texttemplate='%{text}', textposition='outside',
                hovertemplate='<b>%{x}</b><br>PF: %{text}<extra></extra>',
                name='',
            ))
            fig_pf.add_hline(y=1.0, line_dash='dot', line_color=COL_RED, opacity=0.5)
            fig_pf.update_layout(xaxis_title='Family', yaxis_title='Profit Factor',
                                 bargap=0.2, xaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(plotly_dark_layout(fig_pf, max(250, len(df_pf_sorted) * 30 + 40)),
                           use_container_width=True, key="strat_pf_bar")
        st.caption("Dotted line at PF = 1.0 — breakeven threshold")

    # ── P&L by family ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        st.markdown("### P&L by Strategy Family")
        df_fam = data['trades_df'].groupby('strategy_type').agg(
            pnl=('profit_net', 'sum'), trades=('profit_net', 'count')
        ).reset_index()
        df_fam = df_fam.sort_values('pnl', ascending=True).reset_index(drop=True)
        colors_fam = make_gradient_colors(df_fam['pnl'].tolist())

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df_fam['strategy_type'], y=df_fam['pnl'],
            marker_color=colors_fam,
            text=df_fam['trades'], textposition='outside',
            texttemplate='%{text}',
            hovertemplate='<b>%{x}</b><br>PnL: %{y:,.1f}<br>Trades: %{text}<extra></extra>',
            name='',
        ))
        fig2.add_hline(y=0, line_dash='dot', line_color=COL_MUTED, opacity=0.4)
        fig2.update_layout(xaxis_title='Family', yaxis_title='P&L (RUB)',
                            bargap=0.2, xaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(plotly_dark_layout(fig2, 380), use_container_width=True,
                       key="strat_family_pnl_bar")

    # ── Active strategies table ──
    # Active Strategies / Allocation by symbol / Trade Log — выключены 25.10 (не используются).
        # Код ниже выключен через `if False and ...` — при желании строки удалить физически.
    if False and data['active_strategies']:  # ── Active Strategies — убрана 25.10
        df_active = pd.DataFrame(data['active_strategies'])
        df_active = df_active.sort_values('lot', ascending=False).reset_index(drop=True)
        df_active['status'] = df_active['has_position'].apply(
            lambda x: 'LONG' if x else 'WAITING'
        )
        display_cols = ['status', 'symbol', 'type', 'param_key', 'lot', 'magic']
        cols_to_show = [c for c in display_cols if c in df_active.columns]
        
        st.dataframe(
            df_active[cols_to_show], use_container_width=True,
            column_config={
                'lot': st.column_config.NumberColumn(format="%.2f"),
                # (убрано: конфиг колонки, которой нет в этой таблице)
                'magic': st.column_config.NumberColumn(format="%.0f"),
            }, hide_index=True,
        )

        st.markdown("### Allocation by Symbol")
        by_symbol = df_active.groupby('symbol').agg(
            strategies=('symbol', 'count'),
            lots=('lot', 'sum'),
            in_position=('has_position', 'sum'),
        ).reset_index()
        st.dataframe(by_symbol, use_container_width=True, hide_index=True)
    else:
        pass  # info «No active strategies» не показываем — таблицы убраны

    # ── Trade log ──
    pass  # заголовок «Trade Log — Last 50» убран вместе с таблицей
    if False and not data['trades_df'].empty:  # Trade Log — убрана 25.10 (не используется)
        show_cols = ['timestamp', 'symbol', 'strategy_type', 'param_key',
                     'type', 'entry', 'volume', 'price',
                     'profit', 'commission', 'swap', 'profit_net', 'magic']
        cols_available = [c for c in show_cols if c in data['trades_df'].columns]
        st.dataframe(
            data['trades_df'][cols_available].tail(50),
            use_container_width=True, hide_index=True,
            column_config={
                'timestamp': st.column_config.DatetimeColumn(format="DD.MM.YYYY HH:mm:ss"),
                'price': st.column_config.NumberColumn(format="%.5f"),
                'volume': st.column_config.NumberColumn(format="%.2f"),
                'profit': st.column_config.NumberColumn(format="%.2f"),
                'commission': st.column_config.NumberColumn(format="%.2f"),
                'swap': st.column_config.NumberColumn(format="%.2f"),
                'profit_net': st.column_config.NumberColumn(format="%.2f"),
            },
        )
    else:
        pass  # info «No trades in history…» не показываем — таблица убрана


# ═══════════════════════════════════════════════════════════════
#  3D LANDSCAPE
# ═══════════════════════════════════════════════════════════════
if False:  # 3D LANDSCAPE: вкладка убрана; код физически удалит python tools/dashboard_tabs.py
    st.markdown("### Strategy Landscape — 3D")

    if not data:
        st.warning("No data.")
        st.stop()

    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        df_3d = data['trades_df'].groupby(
            ['symbol', 'strategy_type', 'param_key']
        ).agg(
            pnl=('profit_net', 'sum'),
            trades=('profit_net', 'count'),
            volatility=('profit_net', 'std'),
            wins=('profit_net', lambda x: (x > 0).sum()),
            losses=('profit_net', lambda x: (x < 0).sum()),
        ).reset_index()

        df_3d['name'] = df_3d['symbol'].str.replace('rfd', '') + '|' + df_3d['strategy_type']
        df_3d['volatility'] = df_3d['volatility'].fillna(0)
        df_3d['profit_factor'] = df_3d.apply(
            lambda r: abs(r['wins'] / r['losses']) if r['losses'] > 0
            else (10.0 if r['wins'] > 0 else 0), axis=1,
        )

        pnl_vals = df_3d['pnl']
        max_abs_pnl = max(1.0, float(df_3d['pnl'].abs().max()))
        colors_3d = []
        for pnl in pnl_vals:
            if pnl >= 0:
                ratio = min(pnl / max_abs_pnl, 1.0)
                colors_3d.append(f'rgb({int(46 + 30*ratio)}, {int(150 + 35*ratio)}, {int(67 + 30*ratio)})')
            else:
                ratio = min(-pnl / max_abs_pnl, 1.0)
                colors_3d.append(f'rgb({int(218 + 25*ratio)}, {int(54 + 40*ratio)}, {int(51 + 20*ratio)})')

        sizes = df_3d['trades'].clip(lower=1) * 9

        fig_3d = go.Figure()
        fig_3d.add_trace(go.Scatter3d(
            x=df_3d['pnl'], y=df_3d['volatility'], z=df_3d['trades'],
            mode='markers+text',
            marker=dict(size=sizes, color=colors_3d, line=dict(width=0.5, color=COL_PANEL),
                        opacity=0.85),
            text=df_3d['name'], textposition='top center',
            textfont=dict(size=12, color=COL_MUTED),
            hovertemplate='<b>%{text}</b><br>PnL: %{x:,.1f}<br>Vol: %{y:,.1f}<br>Trades: %{z}<extra></extra>',
            name='',
        ))

        fig_3d.add_trace(go.Scatter3d(
            x=[0, 0], y=[0, df_3d['volatility'].max() * 1.1 if df_3d['volatility'].max() > 0 else 1],
            z=[0, df_3d['trades'].max() * 1.1 if df_3d['trades'].max() > 0 else 1],
            mode='lines', line=dict(color=COL_MUTED, width=1, dash='dot'),
            showlegend=False, hoverinfo='skip',
        ))

        fig_3d.update_layout(
            scene=dict(
                xaxis=dict(title='P&L', backgroundcolor=COL_PANEL, gridcolor=COL_GRID, showbackground=True,
                           tickfont=dict(size=16, color=COL_MUTED), title_font=dict(size=18)),
                yaxis=dict(title='Volatility', backgroundcolor=COL_PANEL, gridcolor=COL_GRID, showbackground=True,
                           tickfont=dict(size=16, color=COL_MUTED), title_font=dict(size=18)),
                zaxis=dict(title='Trades', backgroundcolor=COL_PANEL, gridcolor=COL_GRID, showbackground=True,
                           tickfont=dict(size=16, color=COL_MUTED), title_font=dict(size=18)),
                camera=dict(eye=dict(x=1.5, y=1.5, z=0.8)),
            ),
            paper_bgcolor=COL_PANEL, height=650,
            margin=dict(l=0, r=0, t=10, b=0),
            font=dict(color=COL_TEXT, size=16),
            showlegend=False,
        )
        st.plotly_chart(fig_3d, use_container_width=True, key="3d_landscape")

        with st.expander("Reading the chart"):
            st.markdown("""
            | Dimension | Axis | Meaning |
            |-----------|------|---------|
            | P&L | X | Cumulative profit/loss |
            | Volatility | Y | Return dispersion |
            | Trades | Z | Activity volume |
            | Color | — | PnL >= 0 green, PnL < 0 red (яркость = величина) |
            | Size | — | Proportional to trade count |

            **Scale up:** green, large, low volatility (near Y=0).
            **Scale down:** red (negative PnL), high volatility.
            **Unreliable:** small dots — insufficient sample size.
            """)

    else:
        st.info("No data for 3D model.")


# ═══════════════════════════════════════════════════════════════
#  STRATEGY TREE
# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
#  STRATEGY TREE
# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
#  STRATEGY TREE
# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
#  STRATEGY TREE
# ═══════════════════════════════════════════════════════════════
with tab_tree:
    # Заголовок «### Strategy Tree» убран: имя вкладки уже видно сверху — дубль не нужен.

    if not data:
        st.warning("No data.")
        st.stop()

    trades_df = data.get('trades_df')
    if trades_df is None or trades_df.empty or not PLOTLY_AVAILABLE:
        if not PLOTLY_AVAILABLE:
            st.warning("Plotly недоступен — Strategy Tree не может быть построен.")
            st.stop()
        _ds = data.get('dash_stats') or {}
        st.info(
            "**Дерево пустое.** Оно строится только из **закрытых** позиций наших стратегий "
            "(magic 770000–869999, символы `*rfd`) за выбранное окно слайдера.\n\n"
            + f"- Окно: {str(_ds.get('window_from', '?'))[:10]} .. {str(_ds.get('window_to', '?'))[:10]} "
            f"(Lookback {_ds.get('days_back', '?')} дн.)\n"
            + f"- Сделок в окне (все magic): **{_ds.get('n_deals_raw', '?')}**\n"
            + f"- Наших (magic+rfd): **{_ds.get('n_deals_ours', '?')}**\n"
            + f"- **Закрытых позиций: {_ds.get('n_closed_positions', '?')}** ← нужно для дерева\n"
            + f"- Открытых позиций: **{_ds.get('n_open_positions', '?')}** (в дерево не попадают)\n\n"
            + "**Причины:** 1) слишком маленький Lookback; 2) в окне нет закрытий; "
            "3) дашборд подключён не к тому терминалу/счёту."
        )
        st.stop()

    # ── Копия и нормализация ────────────────────────────────────
    df_tree = trades_df.copy()

    # Проверяем, что колонка profit_net существует и числовая
    if 'profit_net' not in df_tree.columns:
        st.error(
            "❌ Колонка `profit_net` не найдена в trades_df.\n\n"
            f"Доступные колонки: `{df_tree.columns.tolist()}`"
        )
        st.stop()

    df_tree['profit_net'] = pd.to_numeric(df_tree['profit_net'], errors='coerce').fillna(0)

    # Нормализация категориальных колонок: строки, без NaN/пустот
    for col in ['strategy_type', 'symbol', 'param_key']:
        if col in df_tree.columns:
            df_tree[col] = (
                df_tree[col]
                .astype(str)
                .str.strip()
                .replace(['nan', 'None', '', 'NaN'], 'Unknown')
            )
        else:
            df_tree[col] = 'Unknown'

    # ── Диагностика (можно закомментировать, когда всё заработает) ──
    total_pnl_raw = float(df_tree['profit_net'].sum())
    nonzero_count = int((df_tree['profit_net'] != 0).sum())

    if total_pnl_raw == 0 and nonzero_count == 0:
        st.warning(
            f"Все значения `profit_net` равны нулю. "
            f"Сделок: {len(df_tree)}, но PnL везде 0 — дерево будет пустым.\n\n"
            "Возможные причины:\n"
            "- Колонка называется иначе (проверь список колонок выше)\n"
            "- Данные ещё не досчитаны (профит не зафиксирован)\n"
            "- Подключён не тот терминал/счёт"
        )
        with st.expander("Отладка"):
            st.write(f"Колонки: {df_tree.columns.tolist()}")
            st.write(f"Строк: {len(df_tree)}")
            st.write(f"Сумма profit_net: {total_pnl_raw}")
            st.dataframe(df_tree[['strategy_type', 'symbol', 'param_key', 'profit_net']].head(20))
        st.stop()

    # ── Агрегации ───────────────────────────────────────────────
    top_k = 3

    grp_fam = (
        df_tree.groupby('strategy_type')['profit_net']
        .agg(['sum', 'count'])
        .reset_index()
        .rename(columns={'sum': 'pnl', 'count': 'trades'})
    )
    grp_sym = (
        df_tree.groupby(['strategy_type', 'symbol'])['profit_net']
        .agg(['sum', 'count'])
        .reset_index()
        .rename(columns={'sum': 'pnl', 'count': 'trades'})
    )
    grp_strat = (
        df_tree.groupby(['strategy_type', 'symbol', 'param_key'])['profit_net']
        .agg(['sum', 'count'])
        .reset_index()
        .rename(columns={'sum': 'pnl', 'count': 'trades'})
    )

    # ── Построение узлов ────────────────────────────────────────
    def safe_id(prefix, *parts):
        s = '_'.join(str(p) for p in parts)
        for ch in ['/', '\\', '.', ' ', '-', '(', ')', ',', ':', ';', "'", '"']:
            s = s.replace(ch, '_')
        s = '_'.join(s.split('_'))  # схлопываем повторяющиеся подчёркивания
        return f"{prefix}_{s}"
    # 




    # ── Объём: всего / средний недельный темп прироста (week-over-week) ──
    # Слева — суммарный объём за всё окно (закрытые позиции), справа — средний
    # недельный темп прироста объёма, %.
    if 'volume' not in df_tree.columns:
        # Без колонки объёма дерево не должно падать: объёмная ячейка покажет 0/—.
        df_tree['volume'] = 0.0
    df_tree['volume'] = pd.to_numeric(df_tree['volume'], errors='coerce').fillna(0.0)
    if 'timestamp' in df_tree.columns:
        _ts_col = 'timestamp'
    elif 'time' in df_tree.columns:
        _ts_col = 'time'
    else:
        # Ни одной метки времени — не падаем: недельный темп прироста будет 0.0%.
        df_tree['time'] = pd.NaT
        _ts_col = 'time'
    df_tree['_cdate'] = pd.to_datetime(df_tree[_ts_col], unit=('s' if _ts_col == 'time' else None)).dt.normalize()

    def _vol_cell(sub):
        if len(sub) == 0:
            return '0/—'
        total = float(sub['volume'].sum())
        vstr = f'{total:.2f}'.rstrip('0').rstrip('.') or '0'
        weekly = sub.groupby(sub['_cdate'].dt.to_period('W'))['volume'].sum().sort_index()
        w = weekly.tolist()
        rates = [(w[i] - w[i - 1]) / w[i - 1] for i in range(1, len(w)) if w[i - 1] > 0]
        gstr = f'{sum(rates) / len(rates) * 100.0:+.1f}%' if rates else '0.0%'
        return f'{vstr}/{gstr}'

    def _vc_fam(_t):
        return _vol_cell(df_tree[df_tree['strategy_type'] == _t])

    def _vc_sym(_t, _sym):
        return _vol_cell(df_tree[(df_tree['strategy_type'] == _t) & (df_tree['symbol'] == _sym)])

    def _vc_str(_t, _sym, _pk):
        return _vol_cell(df_tree[(df_tree['strategy_type'] == _t) & (df_tree['symbol'] == _sym) & (df_tree['param_key'] == _pk)])

    nodes = []

    # Корень
    total_pnl = float(df_tree['profit_net'].sum())
    total_vol = _vol_cell(df_tree)
    nodes.append({
        'id': 'total',
        'parent': '',
        'label': f'Total  {total_pnl:+,.0f} ₽ · {total_vol}',
        'pnl': total_pnl,
        'size': max(abs(total_pnl), 1.0),  # минимум 1, чтобы не было нуля
    })

    # Уровень: семьи стратегий
    for _, f in grp_fam.sort_values('pnl', ascending=False).iterrows():
        t = f['strategy_type']
        fam_id = safe_id('fam', t)
        nodes.append({
            'id': fam_id,
            'parent': 'total',
            'label': f'{t}  {f["pnl"]:+,.0f} ₽ · {_vc_fam(t)}',
            'pnl': float(f['pnl']),
            'size': max(abs(float(f['pnl'])), 1.0),
        })

    # Уровень: символы внутри семьи
    for _, s in grp_sym.sort_values('pnl', ascending=False).iterrows():
        t, sym = s['strategy_type'], s['symbol']
        sym_id = safe_id('fs', t, sym)
        parent_id = safe_id('fam', t)
        nodes.append({
            'id': sym_id,
            'parent': parent_id,
            'label': f'{sym}  {s["pnl"]:+,.0f} ₽ · {_vc_sym(t, sym)}',
            'pnl': float(s['pnl']),
            'size': max(abs(float(s['pnl'])), 1.0),
        })

    # Уровень: конкретные стратегии (top_k + Others)
    for (t, sym), g in grp_strat.groupby(['strategy_type', 'symbol']):
        parent_id = safe_id('fs', t, sym)
        g_sorted = g.sort_values('pnl', ascending=False)
        top = g_sorted.head(top_k)
        rest = g_sorted.iloc[top_k:]

        for _, r in top.iterrows():
            strat_id = safe_id('st', t, sym, r['param_key'])
            nodes.append({
                'id': strat_id,
                'parent': parent_id,
                'label': f'{r["param_key"]}  {r["pnl"]:+,.0f} ₽ · {_vc_str(t, sym, r["param_key"])}',
                'pnl': float(r['pnl']),
                'size': max(abs(float(r['pnl'])), 1.0),
            })

        if not rest.empty:
            r_pnl = float(rest['pnl'].sum())
            _rest_sub = df_tree[(df_tree['strategy_type'] == t) & (df_tree['symbol'] == sym) & (df_tree['param_key'].isin(set(rest['param_key'])))]
            _rest_vol = _vol_cell(_rest_sub)
            others_id = safe_id('st_others', t, sym)
            nodes.append({
                'id': others_id,
                'parent': parent_id,
                'label': f'Others ({len(rest)})  {r_pnl:+,.0f} ₽ · {_rest_vol}',
                'pnl': r_pnl,
                'size': max(abs(r_pnl), 1.0),
            })

    # ── Проверка целостности иерархии ──────────────────────────
    ids = [n['id'] for n in nodes]
    parents = [n['parent'] for n in nodes]
    labels = [n['label'] for n in nodes]
    pnls = [n['pnl'] for n in nodes]
    values = [n['size'] for n in nodes]

    # ── Согласование площадей (иначе treemap валится и вкладка «не грузится») ──
    # Plotly требует: значение родителя ≥ суммы значений детей. Площадь = |PnL|,
    # а внутри семьи/символа плюсы и минусы гасят друг друга (дети +300 и −200
    # при родителе +100), поэтому условие нарушалось и go.Treemap падал с
    # ValueError «Parent value must be greater than or equal to sum of children
    # values». Сначала согласуем СНИЗУ ВВЕРХ (родитель = Σ детей) — требование
    # Plotly, затем пересчитываем СВЕРХУ ВНИЗ по |net PnL| (см. _alloc ниже).
    _kids = {}
    for _n in nodes:
        _kids.setdefault(_n['parent'], []).append(_n['id'])
    _by_id = {_n['id']: _n for _n in nodes}

    def _fit_sizes(_nid):
        _ch = _kids.get(_nid, [])
        if not _ch:
            return _by_id[_nid]['size']
        _sum_ch = sum(_fit_sizes(_c) for _c in _ch)
        _by_id[_nid]['size'] = _sum_ch
        return _sum_ch

    _fit_sizes('total')  # низ-вверх: parent = Σ детей (иначе Plotly ругается)
    # ── Площади сверху вниз: пропорционально |ЧИСТОМУ PnL| внутри родителя ──
    # _fit_sizes даёт семье площадь = Σ|PnL| её стратегий (валовый оборот в обе
    # стороны), поэтому семья из многих мелких плюсов/минусов (+11k в итоге)
    # выглядела крупнее семьи с реально большим итогом. Пересчитываем бюджет
    # родителя на детей по весу |net PnL|: площадь узла ≈ модуль его итога,
    # а parent = Σ детей сохраняется (требование branchvalues='total').
    def _alloc(_nid, _budget):
        _by_id[_nid]['size'] = _budget
        _ch = _kids.get(_nid, [])
        if not _ch:
            return
        _w = {_c: max(abs(float(_by_id[_c]['pnl'])), 1e-9) for _c in _ch}
        _sw = sum(_w.values()) or 1.0
        for _c in _ch:
            _alloc(_c, _budget * _w[_c] / _sw)

    _alloc('total', max(abs(total_pnl), 1.0))
    values = [n['size'] for n in nodes]

    # Проверка: нет ли дубликатов ID
    if len(ids) != len(set(ids)):
        dupes = [x for x in ids if ids.count(x) > 1]
        st.warning(f"Дубликаты ID в дереве: {dupes[:5]}")

    # Проверка: все ли parent ссылаются на существующий ID (или пустые для корня)
    ids_set = set(ids)
    orphans = [p for p in parents if p and p not in ids_set]
    if orphans:
        st.warning(f"Orphan parents (нет родителя): {orphans[:5]}")

    # ── Цвета узлов (градиент PnL) ─────────────────────────────
    _pos_vals = [p for p in pnls if p > 0]
    _neg_vals = [-p for p in pnls if p < 0]
    _max_pos = max(_pos_vals) if _pos_vals else 1.0
    _max_neg = max(_neg_vals) if _neg_vals else 1.0
    node_colors = []
    for _p in pnls:
        if _p == 0:
            node_colors.append('rgb(45, 52, 60)')
        elif _p > 0:
            _r = (_p / _max_pos) ** 0.5
            node_colors.append(
                f'rgb({int(18 + 56 * _r)}, {int(48 + 174 * _r)}, {int(30 + 88 * _r)})'
            )
        else:
            _r = (-_p / _max_neg) ** 0.5
            node_colors.append(
                f'rgb({int(56 + 174 * _r)}, {int(22 + 50 * _r)}, {int(22 + 44 * _r)})'
            )

    # ── Перевес по дереву: зелёные / красные категории (symbol + family) ──
    # Считаем по РЕАЛЬНЫМ закрытым сделкам окна (то же, из чего строится treemap):
    # PnL — сумма profit_net, объём — сумма volume (лоты закрытых сделок).
    # В Daily Plan эти же метрики считаются по ОБЪЁМУ ПЛАНА (лоты), здесь — по факту.
    _tcat = (df_tree.groupby(['symbol', 'strategy_type'])
             .agg(pnl=('profit_net', 'sum'), lots=('volume', 'sum'))
             .reset_index())
    _t_tot = float(_tcat['lots'].sum())
    _t_g_pnl = float(_tcat.loc[_tcat['pnl'] > 0, 'pnl'].sum())
    _t_r_pnl = float(_tcat.loc[_tcat['pnl'] < 0, 'pnl'].sum())
    _t_g_lot = float(_tcat.loc[_tcat['pnl'] > 0, 'lots'].sum())
    _t_r_lot = float(_tcat.loc[_tcat['pnl'] < 0, 'lots'].sum())
    _t_g_n = int((_tcat['pnl'] > 0).sum())
    _t_r_n = int((_tcat['pnl'] < 0).sum())
    _t_bal = _t_g_pnl + _t_r_pnl
    _t_r_pct = (100.0 * _t_r_lot / _t_tot) if _t_tot > 0 else None
    # Четыре карточки в РЯД. st.metric не умеет красить значение (только дельту),
    # поэтому ниже metric_card: он красит цифру по знаку и держит min-height.
    # Рендер строго внутри with _tN: иначе карточки падают на уровень контейнера
    # и встают в столбец во всю ширину — ровно это и было видно.
    # Сколько плиток реально на карте: семьи (rf, percentile, pinbar…) и листья
    # (стратегии param_key + бакеты Others). Считаем по тем же nodes, из которых
    # строится treemap, поэтому цифра совпадает с числом блоков на карте.
    _n_fam = sum(1 for _n in nodes if _n['parent'] == 'total')
    _n_sym = sum(1 for _n in nodes if str(_n['parent']).startswith('fam_'))
    _n_leaf = sum(1 for _n in nodes if not _kids.get(_n['id']))

    _t1, _t2, _t3, _t4 = st.columns(4)
    with _t1:
        metric_card("Зелёные", f"{_t_g_pnl:+,.0f} ₽".replace(',', ' '),
                    color=COL_GREEN_LT,
                    sub=f"{_t_g_lot:.2f} лот. · {_t_g_n} кат.")

    with _t2:
        metric_card("Красные", f"{_t_r_pnl:+,.0f} ₽".replace(',', ' ').replace('-', '−'),
                    color=COL_RED_LT,
                    sub=f"{_t_r_lot:.2f} лот. · {_t_r_n} кат.")
    with _t3:
        metric_card("Перевес", f"{_t_bal:+,.0f} ₽".replace(',', ' ').replace('-', '−'),
                    color=(COL_GREEN_LT if _t_bal >= 0 else COL_RED_LT),
                    sub=(f"{_t_r_pct:.0f}% объёма у красных" if _t_r_pct is not None
                         else "зелёные + красные"))
    with _t4:
        metric_card("Стратегий на карте", f"{_n_fam}",
                    color=COL_BLUE,
                    sub=f"{_n_sym} симв. · {_n_leaf} плиток")
    st.markdown("<div style='height:0.4rem;'></div>",
                 unsafe_allow_html=True)













    # CSS .st-key-tree_metrics больше не нужен — цвет задаёт metric_card.

    # ── Treemap ────────────────────────────────────────────────
    fig_tree = go.Figure(go.Treemap(
        ids=ids,
        parents=parents,
        labels=labels,
        values=values,
        branchvalues='total',  # родитель = Σ детей (см. _fit_sizes/_alloc): 'remainder' падал
        maxdepth=4,
        textinfo='label',
        textfont=dict(size=12, color=COL_TEXT),
        marker=dict(
            colors=node_colors,
            showscale=False,
            line=dict(width=1, color=COL_BG),
        ),
        hovertemplate='%{label}<br>PnL: %{customdata:+,.0f} ₽<extra></extra>',
        customdata=pnls,
    ))

    fig_tree.update_layout(
        paper_bgcolor=COL_PANEL,
        height=720,
        margin=dict(l=0, r=0, t=10, b=0),
        font=dict(color=COL_TEXT, size=12),
    )

    # Откат: width='stretch' → use_container_width (как во всех графиках файла).
    # Если treemap всё же не отрисуется — вкладка не должна оставаться пустой:
    # показываем ту же иерархию таблицей (id/parent/|PnL|), чтобы данные были видны.
    try:
        st.plotly_chart(fig_tree, use_container_width=True, key="strategy_tree")
    except Exception as _e_tree:
        st.error(f"⚠ Treemap не отрисовался: {_e_tree!r}")
        st.dataframe(pd.DataFrame({'id': ids, 'parent': parents, 'label': labels,
                                   'size': values, 'pnl': pnls}),
                     use_container_width=True, hide_index=True)

    with st.expander("Reading the Tree — что означают записи", expanded=False):
        st.markdown(
        """
**Иерархия узлов (4 уровня + свёртка):**

| Уровень | Что это | Пример подписи |
|---|---|---|
| **Total** | Вся книга: сумма PnL всех закрытых сделок за окно | `Total  +21 500 ₽ · 48.2/+3.1%` |
| **Family** | Семейство стратегий (`strategy_type`) | `percentile … ₽ · 12.0/+2.4%` |
| **Symbol** | Семейство × символ | `EURUSDrfd … ₽ · 5.0/-1.1%` |
| **Strategy** | Конкретная комбинация `param_key` | `lb200_nb5_th0.60 … ₽ · 3.0/=0.0%` |
| **Others** | Свёртка «хвоста»: все комбинации данного символ+семейство, кроме топ‑3 по PnL | агрегат остальных |

**Анатомия подписи узла:** `ИМЯ  ±PnL ₽ · ОБЪЁМ`
- **±PnL** — чистый реализованный PnL (₽) за окно. `+` прибыль, `−` убыток. Это **реальные закрытые сделки** из журнала (не бэктест).
- **часть после «·»** — объёмная ячейка `ВСЕГО/±%` (разбор ниже).

**Площадь узла** = |чистый PnL| узла в долях родителя. Сравнивать площади между собой
можно только внутри одного родителя (семьи/символа): там дети делят его бюджет
пропорционально |PnL|. Больше площадь = больше модуль прибыли/убытка, **не** больше объём.

**Цвет** — градиент по PnL, не бинарный «зелёный/красный»:
- тёмно‑зелёный → ярко‑зелёный: чем больше прибыль (ярче = дальше от нуля);
- тёмно‑красный → ярко‑красный: чем больше убыток;
- серый = ровно `0`.
Нормализация идёт **раздельно** для плюсов и минусов — крупный плюс не «гасит» мелкие минусы.

**Объёмная ячейка `ВСЕГО/±%`:**
- **ВСЕГО** — суммарный объём (лоты) всех закрытых сделок узла за окно;
- **±%** — средний **недельный темп прироста** объёма (week‑over‑week): средний % изменения объёма неделя‑к‑неделе внутри окна (`+3.2%` — разгон, `−5%` — затухание, `=0.0%` — ровно).

> ⚠️ Растущий `±%` у **убыточного** (красного) узла — это не «рост эффективности».
> Обычно это значит, что штурвал ещё не переложил объём: он работает **раз в ночь**,
> применяет квоты только к стратегиям **без открытой позиции** и по назначенным квотам.
> Поэтому объём убыточных стратегий может ещё расти, пока перекладка «доезжает».

**Hover (наведение):** полное имя узла + точный PnL (`PnL: +12 345 ₽`).

**Прочее:**
- окно = `ALLOC_DAYS` дн. из `config.SteeringParams.lookback_days` (сейчас 30) — совпадает с окном Wheel;
- узлы отсортированы по PnL по убыванию;
- число сделок убрано из подписи (объём сверяем со штурвалом), но видно в таблицах Wheel;
- `Others` появляется, когда у символ+семейство больше 3 комбинаций: топ‑3 по PnL показываются отдельно, остальное — в «Others».
        """)
    with st.expander("Reading the tree (кратко)", expanded=False):
        st.markdown("""
        | Level | Shown |
        |-------|-------|
        | Total | Net PnL of all closed trades in the period |
        | Family | Strategy family (RF, LogReg, MA, ...) |
        | Symbol | Family x symbol |
        | Strategy | Top‑3 param_key by PnL + "Others" bucket |

        **Size** — |net PnL| узла: доля родителя пропорциональна |PnL| ребёнка
        (сравнивать площади корректно внутри одной семьи/символа).
        **Color** — PnL gradient: green = profit, red = loss.
        **Volume** — после «·»: `total/±%` — суммарный объём за всё окно и
        средний недельный темп прироста объёма (week-over-week, напр. `12.5/+3.2%`).
        Количество сделок убрано — объём сверяем со штурвалом (Wheel).
        Nodes sorted by PnL descending.
        """)




# ═══════════════════════════════════════════════════════════════
#  STEERING WHEEL
# ═══════════════════════════════════════════════════════════════
with tab_steering:
    if not data:
        st.warning("No data.")
        st.stop()

    st.caption(f"Allocation period: {ALLOC_DAYS} days")


    from wheel import (calculate_steering_wheel_quotas, build_metrics_from_journal, compute_categories,
                       category_label)

    from config import SteeringParams  # ЕДИНЫЙ источник параметров штурвала (config.py)
    steering_cfg = SteeringParams()

    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        # ── Адаптер: trades_df → формат журнала ──
        df_src = data_alloc['trades_df'].copy().reset_index(drop=True)
        if 'profit' in df_src.columns and 'profit_net' in df_src.columns:
            df_src = df_src.drop(columns=['profit'])
        df_src = df_src.rename(columns={'profit_net': 'profit'})
        # Считаем ТОЛЬКО закрывающие сделки (entry='out') — входящие несут profit=0
        # и удваивают счёт, размазывая реальный PnL по группам.
        # ВАЖНО: trades_df из daily_report уже агрегирован по position_id (строка =
        # одна закрытая позиция), а entry там — ЧИСЛО (MT5 enum, DEAL_ENTRY_OUT=1),
        # а не строка 'out'. Сравнение с 'out' давало всегда False → df пустой →
        # wheel не рисовался. Ловим оба формата, чтобы адаптер был устойчивым.
        if 'entry' in df_src.columns:
            def _is_closing(v):
                if isinstance(v, str):
                    return v.strip().lower() == 'out'
                try:
                    return int(v) == 1  # mt5.DEAL_ENTRY_OUT
                except (TypeError, ValueError):
                    return False
            df_src = df_src[df_src['entry'].apply(_is_closing)]
        if 'exit_time' not in df_src.columns and 'timestamp' in df_src.columns:
            df_src['exit_time'] = df_src['timestamp']
        df_src['symbol'] = df_src['symbol'].astype(str)
        df_src['param_key'] = df_src['param_key'].astype(str)

        # ── Боевые функции ──
        strategies_data = compute_categories(df_src)  # PnL за окно аллокации (без n_last) — синхрон с деревом
        # min_trades-фильтр убран: категория берётся по всему окну, как в Strategy Tree.

        if not strategies_data:
            st.info("Нет сделок в журнале для расчёта метрик.")
        else:
            # Текущие квоты из активных стратегий — ПО КАТЕГОРИЯМ «символ + семейство»
            label_map = {s['id']: s.get('label', s['id']) for s in strategies_data}
            if data_alloc.get('active_strategies'):
                df_active = pd.DataFrame(data_alloc['active_strategies'])
                # active_state.json уже содержит 'type' — фолбэк на param_key ломает категорию
                if 'type' not in df_active.columns:
                    df_active['type'] = 'unknown'
                df_active['sid'] = (
                    df_active['symbol'].astype(str) + '_' + df_active['type'].astype(str)
                )
                df_cat = df_active.groupby(['sid', 'symbol', 'type'], as_index=False)['lot'].sum()
                total_lot = df_active['lot'].sum()
                if total_lot > 0:
                    current_quotas = dict(zip(df_cat['sid'], df_cat['lot'] / total_lot))
                else:
                    current_quotas = {}
            else:
                current_quotas = {}

            # Заглушка, если нет активных
            if not current_quotas and strategies_data:
                n = len(strategies_data)
                current_quotas = {s['id']: 1.0 / n for s in strategies_data}

            # min_trades для скоринга берётся из config.SteeringParams.min_trades (не хардкодить здесь)

            new_quotas = calculate_steering_wheel_quotas(
                strategies_data,
                current_quotas,
                {
                    'alpha': steering_cfg.alpha,
                    'min_q': steering_cfg.min_q,
                    'max_q': steering_cfg.max_q,
                    'score_mode': steering_cfg.score_mode,
                    'min_trades': steering_cfg.min_trades,
                    'gamma': getattr(steering_cfg, 'gamma', 1.5),
                    'score_volume_prior': getattr(steering_cfg, 'score_volume_prior', 0.0),
                    # Политика потерь — превью должно совпадать с боем (main.py)
                    'loss_decay': getattr(steering_cfg, 'loss_decay', 0.25),
                    'kill_pnl_pct': getattr(steering_cfg, 'kill_pnl_pct', 0.02),
                    'kill_min_trades': getattr(steering_cfg, 'kill_min_trades', 3),
                    'quota_rub': 0.0,  # рублёвой квоты в превью нет → kill только по параметрам
                },
                known_ids=list(current_quotas.keys()),
            )

            # Сборка DataFrame по ВСЕМ категориям (активные + сделковые) — «символ + семейство»
            metrics_by_id = {s['id']: s for s in strategies_data}
            cat_ids = list(current_quotas.keys())
            for sid in metrics_by_id:
                if sid not in current_quotas:
                    cat_ids.append(sid)

            rows = []
            for sid in cat_ids:
                m = metrics_by_id.get(sid, {})
                sym, fam = (sid.split('_', 1) if '_' in sid else (sid, '?'))
                rows.append({
                    'name': label_map.get(sid, category_label(sym, fam)),
                    'family': m.get('family', fam),
                    'pnl': m.get('pnl', 0.0),
                    'volume': m.get('volume', 0.0),
                    'vol': m.get('vol', 0.0),
                    'trades': m.get('trades', 0),
                    'drawdown': m.get('drawdown', 0.0),
                    'current_quota': current_quotas.get(sid, 0.0),
                    'new_quota': new_quotas.get(sid, 0.0),
                })
            df_sw = pd.DataFrame(rows)

            # ── НОРМАЛИЗАЦИЯ: приводим обе колонки к сумме = 1.0 ──
            # Без этого Plotly pie chart пересчитывает проценты сам,
            # и они не совпадают с таблицей.
            sum_new = df_sw['new_quota'].sum()
            sum_cur = df_sw['current_quota'].sum()
            if sum_new > 0:
                df_sw['new_quota'] = df_sw['new_quota'] / sum_new
            if sum_cur > 0:
                df_sw['current_quota'] = df_sw['current_quota'] / sum_cur

            df_sw['delta'] = df_sw['new_quota'] - df_sw['current_quota']

            # ── SYNC: Strategy Tree → Wheel ─────────────────────────
            # U rank (₽/лот — метрика штурвала) должен совпадать с рангом доли штурвала.
            _sync = df_sw[['name', 'family', 'pnl', 'volume', 'trades', 'current_quota', 'new_quota']].copy()
            _sync['₽/лот'] = _sync.apply(
                lambda r: (r['pnl'] / r['volume']) if r['volume'] else 0.0, axis=1)
            _sync['PnL rank'] = _sync['pnl'].rank(ascending=False, method='min').astype(int)
            _sync['U rank'] = _sync['₽/лот'].rank(ascending=False, method='min').astype(int)
            _sync['Q rank'] = _sync['new_quota'].rank(ascending=False, method='min').astype(int)
            # Sync-блок перенесён вниз; прежнее дублирование отключено (рисовало "None")
            _sdisp = _sync.sort_values('U rank').copy()
            _sdisp['Tree PnL'] = _sdisp['pnl'].round(0).astype(int)
            _sdisp['₽/лот'] = _sdisp['₽/лот'].round(0).astype(int)
            _sdisp['Cur Q %'] = (_sdisp['current_quota'] * 100).round(1)
            _sdisp['New Q %'] = (_sdisp['new_quota'] * 100).round(1)
            _ = None and st.dataframe(
                _sdisp[['U rank', 'name', 'Tree PnL', '₽/лот', 'trades', 'Cur Q %', 'New Q %', 'Q rank']],
                use_container_width=True, hide_index=True)


            df_sw = df_sw.sort_values('delta', ascending=False).reset_index(drop=True)
            n_delta = int((df_sw['delta'].abs() > 1e-4).sum())

            # Для бара Δ берём ТОЛЬКО категории с ненулевым перераспределением
            df_sw_nz = df_sw[df_sw['delta'].abs() > 1e-4].copy()

            # ── Цвета ──
            def quota_color(row):
                d = row['delta']
                if d > 0.01:
                    return COL_GREEN_LT
                elif d > 0:
                    return '#2EA043'
                elif d < -0.01:
                    return COL_RED_LT
                else:
                    return COL_MUTED

            df_sw['color'] = df_sw.apply(quota_color, axis=1)

            # ── Pie charts ──
            col_before, col_after = st.columns(2)

            with col_before:
                st.markdown("#### Current Allocation")
                fig_before = go.Figure(data=[go.Pie(
                    labels=df_sw['name'],
                    values=df_sw['current_quota'],
                    marker=dict(colors=[COL_MUTED] * len(df_sw),
                                line=dict(color=COL_PANEL, width=2)),
                    textinfo='label+percent',
                    textfont=dict(size=13, color=COL_TEXT),
                    hole=0.4, sort=False,
                )])
                fig_before.update_layout(
                    paper_bgcolor=COL_PANEL, height=450,
                    margin=dict(l=10, r=10, t=10, b=10),
                    showlegend=False, font=dict(color=COL_TEXT, size=13),
                )
                st.plotly_chart(fig_before, use_container_width=True,
                                key="steering_pie_before")

            with col_after:
                st.markdown("#### After Steering (indicative)")
                fig_after = go.Figure(data=[go.Pie(
                    labels=df_sw['name'],
                    values=df_sw['new_quota'],
                    marker=dict(colors=df_sw['color'].tolist(),
                                line=dict(color=COL_PANEL, width=2)),
                    textinfo='label+percent',
                    textfont=dict(size=13, color=COL_TEXT),
                    hole=0.4, sort=False,
                )])
                fig_after.update_layout(
                    paper_bgcolor=COL_PANEL, height=450,
                    margin=dict(l=10, r=10, t=10, b=10),
                    showlegend=False, font=dict(color=COL_TEXT, size=13),
                )
                st.plotly_chart(fig_after, use_container_width=True,
                                key="steering_pie_after")

            # ── Bar chart: Δ ──
            st.markdown(f"#### Quota Delta (Δ) — категорий с перераспределением: {len(df_sw_nz)}")
            if df_sw_nz.empty:
                st.info("Перераспределения нет: "
                        f"(цель за окно {ALLOC_DAYS} дн. уже совпала с текущей аллокацией).")
            bar_colors = [COL_GREEN_LT if d > 0 else COL_RED_LT
                          for d in df_sw_nz['delta']]

            fig_delta = go.Figure()
            fig_delta.add_trace(go.Bar(
                x=df_sw_nz['delta'] * 100,
                y=df_sw_nz['name'],
                orientation='h',
                marker_color=bar_colors,
                text=df_sw_nz['delta'].apply(lambda x: f"{x*100:+.1f}%"),
                textposition='outside',
                texttemplate='%{text}',
                hovertemplate='<b>%{y}</b><br>Δ quota: %{text}<extra></extra>',
                name='',
            ))
            fig_delta.add_vline(x=0, line_dash='dot', line_color=COL_MUTED, opacity=0.4)
            fig_delta.update_layout(xaxis_title='Δ quota (%)', bargap=0.12)
            st.plotly_chart(plotly_dark_layout(fig_delta, max(280, len(df_sw_nz) * 26)),
                            use_container_width=True, key="steering_delta_bar")

            # ── Таблица ──
            # ── Sync: Strategy Tree → Wheel (рендер внизу, после пирогов) ──
            st.markdown("#### Sync: Strategy Tree → Wheel")
            st.caption(f"U rank = ранг удельной прибыли (₽/лот, метрика штурвала) ↔ ранг доли штурвала (Q rank). "
                       f"Окно аллокации: {ALLOC_DAYS} дн. Лидер по ₽/лот должен получать максимальную долю "
                       f"(кроме пол/потолок из config и фильтра min_trades={steering_cfg.min_trades}). Tree PnL — абсолютный.")
            st.dataframe(
                _sdisp[['U rank', 'name', 'Tree PnL', '₽/лот', 'trades', 'Cur Q %', 'New Q %', 'Q rank']],
                use_container_width=True, hide_index=True)

            # ── Таблица ──
            st.markdown("#### Detail")
            # ПРАВКА №2: убран target_quota, которого не существует
            df_display = df_sw[['name', 'pnl', 'trades', 'vol', 'drawdown',
                                'current_quota', 'new_quota', 'delta']].copy()
            df_display.columns = ['Strategy', 'P&L', 'Trades', 'Vol', 'DD/PnL',
                                 'Current Q', 'New Q', 'Δ']
            for col in ['Current Q', 'New Q', 'Δ']:
                df_display[col] = (df_display[col] * 100).round(2)
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            st.caption(
                "Зелёные — категории (символ + семейство), получающие больше квоты. "
                "Красные — теряющие долю (α из config.py). "
                f"Окно аллокации: {ALLOC_DAYS} дн. · скоринг: {steering_cfg.score_mode} (штурвал: удельная прибыль ₽ за лот; Tree — абсолютный PnL). "
                "Категории без сделок за окно получают минимум (объём уходит в зелёные зоны дерева). "
                "enabled=False — лоты не меняются, расчёт индикативный."
            )

    else:
        st.info("Нет данных для работы штурвала.")



# ═══════════════════════════════════════════════════════════════
#  PIPELINE
# ═══════════════════════════════════════════════════════════════
if False:  # PIPELINE: вкладка убрана; код физически удалит python tools/dashboard_tabs.py
    st.markdown("### Pipeline — Upcoming Features")

    items = [
        ("Drawdown Chart", "Peak-to-trough equity drawdown. Identifies maximum portfolio stress periods. "
         "Area chart with red fill in drawdown zones."),
        ("Hourly P&L Heatmap", "Matrix: rows = symbols/strategies, columns = hours. Cell color = cumulative P&L. "
         "Identifies time windows with consistent alpha or bleeding."),
        ("Backtest vs Live", "Compares expected backtest metrics with live trading results. "
         "Columns: backtest / actual / deviation / verdict."),
        ("Sharpe by Family", "Risk-adjusted return ranking. Mean daily P&L divided by daily volatility. "
         "Higher Sharpe = better return per unit of risk."),
    ]

    for title, desc in items:
        st.markdown(f"**{title}**")
        st.caption(desc)
        st.markdown("")


# ═══════════════════════════════════════════════════════════════
#  BACKTEST
# ═══════════════════════════════════════════════════════════════
with tab_backtest:
    st.markdown("### Бэктест - график пересчета")

    # Читаем журнал напрямую (без st.cache_data), чтобы данные не «залипали».
    _bt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'checkpoints', 'backtest_history.jsonl')
    _bt_rows = []
    try:
        with open(_bt_path, 'r', encoding='utf-8') as _bt_f:
            for _bt_line in _bt_f:
                _bt_line = _bt_line.strip()
                if not _bt_line:
                    continue
                try:
                    _bt_rows.append(json.loads(_bt_line))
                except (ValueError, TypeError):
                    continue  # битую строку пропускаем
    except (OSError, IOError):
        _bt_rows = []

    if _bt_rows:
        # Состав журнала — видно ВСЕГДА, а не только когда всё отфильтровалось:
        # так сразу понятно, какие прогоны в файле есть (по kind).
        _bt_kinds_all = pd.Series([r.get('kind', 'none') for r in _bt_rows]).value_counts()
        st.caption("В журнале строк: " + ", ".join(
            f"{_k}: {int(_v)}" for _k, _v in _bt_kinds_all.items())
            + f" | файл: {_bt_path}")

    if not _bt_rows:
        st.info("Журнал прогонов пуст — появится после первого бэктеста "
                "(checkpoints/backtest_history.jsonl)")
        # Диагностика: показываем РЕАЛЬНЫЙ путь, который читает вкладка, и есть
        # ли там файл. Без этого непонятно, куда копировать журнал прогонов.
        _bt_exists = os.path.exists(_bt_path)
        _bt_size = os.path.getsize(_bt_path) if _bt_exists else 0
        st.caption("Ищу файл: " + _bt_path + " — "
                   + (f"есть, {_bt_size:,} байт".replace(',', ' ') if _bt_exists
                      else "НЕ НАЙДЕН"))
    else:
        df_bt = pd.DataFrame(_bt_rows)
        if 'kind' not in df_bt.columns:
            df_bt['kind'] = 'full'
        df_bt['ts'] = pd.to_datetime(df_bt.get('ts'), errors='coerce')
        for _bt_c in ['elapsed_sec', 'combos', 'combos_done', 'combos_plan', 'symbols', 'symbols_total', 'results', 'skipped']:
            if _bt_c not in df_bt.columns:
                df_bt[_bt_c] = np.nan
            df_bt[_bt_c] = pd.to_numeric(df_bt[_bt_c], errors='coerce')
        df_bt = df_bt.dropna(subset=['ts'])
        # ── Отсекаем «пустые» ночи (ничего не считалось: всё взято из кэша) ──
        # Раньше они давали в таблице нули и портили средние. Теперь это отдельный
        # счётчик: в статистику прогонов и на график они не попадают.
        _bt_cache_mask = df_bt['combos'].fillna(0) == 0
        _bt_cache_n = int(_bt_cache_mask.sum())
        df_bt = df_bt[~_bt_cache_mask]
        if df_bt.shape[0] == 0:
            st.info("Прогоны с реальным счётом появятся после первого полного или "
                    "полного пересчёта. Пока в журнале нет ни одного полного прогона "
                    f"({_bt_cache_n} ночей).")
            st.stop()
        if df_bt.empty:  # pragma: no cover — пустой журнал уже отсечён выше
            st.info("Журнал прогонов пуст — появится после первого бэктеста "
                    "(checkpoints/backtest_history.jsonl)")
            st.stop()

        df_bt['minutes'] = df_bt['elapsed_sec'] / 60.0
        df_bt['day'] = df_bt['ts'].dt.normalize()
        # Факт = реально посчитанные комбинации ('combos_done'), план = 'combos_plan' (вся корзина).
        # Для старых записей без новых полей — фолбэк на 'combos'.
        df_bt['done'] = df_bt['combos_done'].where(df_bt['combos_done'].notna(), df_bt['combos'])
        df_bt['plan'] = df_bt['combos_plan'].where(df_bt['combos_plan'].notna(), df_bt['combos'])
        # 'skipped'/'symbols_total'/'combos_plan' без fillna: отсутствие данных = «—», а не 0

        _bt_ts_min = df_bt['ts'].min()
        _bt_ts_max = df_bt['ts'].max()
        st.caption(f"Прогонов: {len(df_bt)} | Период: "
                   f"{_bt_ts_min.strftime('%Y-%m-%d %H:%M')} .. "
                   f"{_bt_ts_max.strftime('%Y-%m-%d %H:%M')}")

        # ── Метрики ──
        # не-полные прогоны отсекаем ДО расчёта метрик — см. фильтр ниже
        _bt_full = df_bt[df_bt['kind'] == 'full']
        # Не-полные прогоны с вкладки убраны целиком: они не
        # считают ни одной комбинации и только засоряли статистику/график.
        # На вкладке — ТОЛЬКО полные прогоны. Ничего другого в проекте нет:
        # только full — остальное просто не существует.
        df_bt = df_bt[df_bt['kind'] == 'full']
        if df_bt.shape[0] == 0:
            st.warning("Полных прогонов в журнале нет — "
                    "показывать нечего.")
            _bt_kc = pd.Series([r.get('kind', 'none') for r in _bt_rows]).value_counts()
            st.caption("Строк в журнале: " + ", ".join(
                f"{_k}: {int(_v)}" for _k, _v in _bt_kc.items()) + " | " + _bt_path)
            st.stop()
        # «Последний прогон» пересчитываем ПОСЛЕ отсева не-полных — иначе метрика
        # показывала бы длительность пустого чтения кэша.
        _bt_last = df_bt.sort_values('ts').iloc[-1]
        _bt_avg_all = float(df_bt['minutes'].mean()) if len(df_bt) else 0.0
        _bt_last_min = float(_bt_last['minutes']) if pd.notna(_bt_last['minutes']) else 0.0

        _m1, _m2, _m3 = st.columns(3)
        with _m1:
            st.metric("Прогонов", f"{len(df_bt)}")
        with _m2:
            st.metric("Последний, мин", f"{_bt_last_min:.1f}",
                      delta=f"{_bt_last_min - _bt_avg_all:+.1f}")
            _l_done = _bt_last.get('done')
            _l_plan = _bt_last.get('plan')
            _l_done_s = f"{int(_l_done):,}".replace(',', ' ') if pd.notna(_l_done) else '—'
            _l_plan_s = f"{int(_l_plan):,}".replace(',', ' ') if pd.notna(_l_plan) else '—'
            st.caption(f"последний прогон: считано {_l_done_s} / план {_l_plan_s} комб.")
        with _m3:
            st.metric("Средний полный, мин",
                      f"{_bt_full['minutes'].mean():.1f}" if len(_bt_full) else "—")
            st.caption(f"Полных прогонов: {len(_bt_full)} | "
                       f"полных: {int((df_bt['kind'] == 'full').sum())}")

        # ── График: длительность по дням ──
        if PLOTLY_AVAILABLE:
            def _bt_marker_size(_combos):
                try:
                    _c = max(float(_combos), 1.0)
                except (TypeError, ValueError):
                    _c = 1.0
                _sz = 8 + 6 * (np.log10(_c) / 3.0)
                return float(min(max(_sz, 8.0), 26.0))

            fig_bt = go.Figure()
            for _kind, _name, _color, _symbol in [
                ('full', 'Полный пересчёт', COL_GREEN_LT, 'circle'),
                # (partial/инкремент удалены: в проекте только полные пересчёты)
                # (инкремент удалён: считаем только полный пересчёт)
                # не-полные прогоны на графике не показываем:
                # они не считают ни одной комбинации
            ]:
                _sub = df_bt[df_bt['kind'] == _kind].sort_values('ts')
                if _sub.empty:
                    continue  # второй серии нет — не падаем
                fig_bt.add_trace(go.Scatter(
                    x=_sub['day'],
                    y=_sub['minutes'],
                    mode='markers+lines',
                    name=_name,
                    line=dict(color=_color, width=1.5),
                    marker=dict(
                        size=[_bt_marker_size(_c) for _c in _sub['done']],
                        color=_color, symbol=_symbol,
                        line=dict(width=0.5, color=COL_PANEL),
                    ),
                    text=[f"{int(_c):,}".replace(',', ' ') if pd.notna(_c) else ''
                          for _c in _sub['done']],
                    textposition='top center',
                    textfont=dict(size=11, color=COL_MUTED),
                    customdata=np.stack([
                        _sub['ts'].dt.strftime('%Y-%m-%d %H:%M').to_numpy(),
                        _sub['done'].to_numpy(),
                        _sub['symbols'].to_numpy(),
                        _sub['results'].to_numpy(),
                    ], axis=-1),
                    hovertemplate=(
                        'Дата/время: %{customdata[0]}<br>'
                        f'Тип прогона: {_name}<br>'
                        'Длительность: %{y:.1f} мин<br>'
                        'Считано (факт): %{customdata[1]}<br>'
                        'Символов: %{customdata[2]}<br>'
                        'В пуле: %{customdata[3]}<extra></extra>'
                    ),
                ))
            fig_bt.update_layout(
                xaxis_title='День',
                yaxis_title='Длительность, мин',
                legend=dict(orientation='h', y=1.12, x=0),
            )
            st.plotly_chart(plotly_dark_layout(fig_bt, 420),
                            use_container_width=True, key="backtest_chart")

        # ── Скейл обсчёта: скорость и «цена» 1000 комбинаций по режимам ──
        st.markdown("#### Скейл обсчёта")
        _bt_sc = df_bt.sort_values('ts').copy()
        _bt_sc['cpp'] = _bt_sc['done'] / _bt_sc['elapsed_sec'].replace(0, np.nan)
        _bt_sc['sec1000'] = 1000.0 / _bt_sc['cpp']
        _sc_rows = []
        for _k, _name in [('full', 'Полный')]:
                          # (partial удалён: в проекте только полные пересчёты)
            _s = _bt_sc[_bt_sc['kind'] == _k]
            if _s.empty:
                continue
            _last_s = _s.iloc[-1]
            _sc_rows.append({
                'Режим': _name,
                'Прогонов': len(_s),
                'Медиана, мин': round(float(_s['minutes'].median()), 1),
                'Последний, мин': round(float(_last_s['minutes']), 1),
                'Комб/с (медиана)': (round(float(_s['cpp'].median()), 2)
                                     if _s['cpp'].notna().any() else None),
                'Сек на 1000 комб': (round(float(_s['sec1000'].median()), 1)
                                     if _s['sec1000'].notna().any() else None),
                'Комбинаций (последний)': (int(_last_s['done'])
                                           if pd.notna(_last_s['done']) else 0),
            })
        if _sc_rows:
            st.dataframe(pd.DataFrame(_sc_rows), use_container_width=True, hide_index=True)
            st.caption("«Комб/с» = фактически считано ÷ длительность. «Сек на 1000 комб» — прямой "
                       "масштаб: во сколько обойдётся пересчёт 1000 комбинаций в этом режиме. "
                       "Здесь видно, сколько реально занимает полный пересчёт по ночам.")
        else:
            st.info("Скорость пока не посчитать — нет прогонов с реальным счётом.")
        # Кэш-ночи (реранки по чекпойнтам) в статистике не участвуют — отдельного
        # счётчика «Не в статистике» больше нет (см. фильтр по kind выше).
        # (строка «Не в статистике: N ноч. без счёта» удалена)

        # ── Детализация по ночам (неактивно: только полные пересчёты) ──
        if False:  # инкремента в проекте нет — блок оставлен неактивным
            _inc_rows = []
            for _, _r in df_bt[df_bt['kind'] == 'full'].sort_values('ts').iterrows():
                _inc = _r.get('inc')
                if not isinstance(_inc, dict) or not _inc:
                    continue
                _win = int(_inc.get('window_bars') or 0)
                _slice = int(_inc.get('slice_bars') or 0)
                _el = _r.get('elapsed_sec')
                _dn = _r.get('done')
                _inc_rows.append({
                    'Дата/время': _r['ts'].strftime('%Y-%m-%d %H:%M'),
                    'Мин': round(float(_r['minutes']), 1),
                    'Символов': int(_inc.get('inc_symbols') or 0),
                    'Семейств inc/full': (f"{int(_inc.get('inc_families') or 0)} / "
                                          f"{int(_inc.get('full_families') or 0)}"),
                    'Обновлено комб.': int(_inc.get('inc_combos') or 0),
                    'Срез, бар': _slice,
                    'Окно, бар': _win,
                    'Срез/окно': (f"{_slice / _win * 100:.0f}%" if _win else '—'),
                    'Warm-up / новых': (f"{int(_inc.get('warmup_bars') or 0)} / "
                                        f"{int(_inc.get('bars_new') or 0)}"),
                    'Комб/с': (round(float(_dn) / float(_el), 2)
                               if (pd.notna(_el) and float(_el) > 0 and pd.notna(_dn)) else None),
                })
            if _inc_rows:
                st.markdown("#### Детали по ночам")
                st.dataframe(pd.DataFrame(_inc_rows), use_container_width=True, hide_index=True)
                st.caption("«Срез/окно» — какая доля 30-дневного окна реально пересчитывалась: "
                           "чем меньше, тем дешевле ночь. «Семейств inc/full» — сколько семейств "
                           "считалось срезом, сколько полным окном (cum/model всегда полным).")
            else:
                st.caption("Прогоны есть, но без деталей (старый формат журнала).")

        # ── Таблица-лог ──
        _bt_log = df_bt.sort_values('ts', ascending=False).copy()
        st.caption("«Считано» — реально посчитанные комбинации (факт). «План» — вся корзина комбинаций (пересчёт + чекпойнты). "
                   "«Символы» — сколько символов пересчитано заново. «В корзине» — символов всего (пересчёт + чекпойнты). «Пропущ.» — символов взято из чекпоинтов. "
                   "«В пуле» — сколько стратегий в пуле результатов после мержа/дедупа. "
                   "Ночи без счёта вкладка не показывает.")
        _bt_log['Дата/время'] = _bt_log['ts'].dt.strftime('%Y-%m-%d %H:%M')
        _bt_log['Тип'] = _bt_log['kind'].map({'full': 'Полный'})
                                              # (инкремент удалён: остаётся только полный пересчёт)
        _bt_log['Длительность (мин)'] = _bt_log['minutes'].round(1)
        # Скорость режима: фактически посчитанные комбинации в секунду.
        _bt_log['Комб/с'] = (_bt_log['done'] / _bt_log['elapsed_sec'].replace(0, np.nan)).round(2)
        def _bt_fmt(v):
            return int(v) if pd.notna(v) else '—'
        _bt_log['Считано'] = _bt_log['done'].apply(_bt_fmt)
        _bt_log['План'] = _bt_log['plan'].apply(_bt_fmt)
        _bt_log['Символы'] = _bt_log['symbols'].apply(_bt_fmt)
        _bt_log['В корзине'] = _bt_log['symbols_total'].apply(_bt_fmt)
        _bt_log['Пропущ.'] = _bt_log['skipped'].apply(_bt_fmt)
        _bt_log['В пуле'] = _bt_log['results'].apply(_bt_fmt)

        st.dataframe(
            _bt_log[['Дата/время', 'Тип', 'Длительность (мин)', 'Комб/с',
                     'Считано', 'План', 'Символы', 'В корзине', 'Пропущ.', 'В пуле']],
            use_container_width=True, hide_index=True,
        )
