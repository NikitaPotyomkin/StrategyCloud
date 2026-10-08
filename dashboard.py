import streamlit as st
import pandas as pd
import numpy as np
import os
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

# ── Палитра (институциональная) ──
COL_BG       = '#0E1117'
COL_PANEL    = '#161B22'
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


# ── Кастомный CSS ──
st.markdown("""
<style>
    /* Тёмный фон */
    .stApp { background-color: #0E1117; }

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
        background-color: #161B22;
        border-radius: 0;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 12px 24px;
        background-color: #161B22;
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
        background-color: #161B22;
        border-bottom: 2px solid #388bfd;
    }

    /* Таблицы */
    .stDataFrame [data-testid="stDataFrame"] {
        background-color: #161B22;
    }

    /* Сайдбар */
    .stSidebar > div:first-child {
        background-color: #161B22;
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
    pos_light = (30, 40, 30)
    neg_base = hex_to_rgb(negative_hex)
    neg_light = (40, 28, 28)

    colors = []
    for v in values:
        ratio = abs(v) / max_abs
        if v >= 0:
            r = int(pos_light[0] + (pos_base[0] - pos_light[0]) * ratio)
            g = int(pos_light[1] + (pos_base[1] - pos_light[1]) * ratio)
            b = int(pos_light[2] + (pos_base[2] - pos_light[2]) * ratio)
        else:
            r = int(neg_light[0] + (neg_base[0] - neg_light[0]) * ratio)
            g = int(neg_light[1] + (neg_base[1] - neg_light[1]) * ratio)
            b = int(neg_light[2] + (neg_base[2] - neg_light[2]) * ratio)
        colors.append(f'rgb({r}, {g}, {b})')
    return colors


def plotly_dark_layout(fig, height=400):
    """Применяет тёмную институциональную тему к plotly-фигуре."""
    fig.update_layout(
        height=height,
        template='plotly_dark',
        paper_bgcolor=COL_PANEL,
        plot_bgcolor=COL_PANEL,
        font=dict(color=COL_TEXT, family='SF Mono, Cascadia Code, Consolas, monospace', size=18),
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


# ── Заголовок ──
col_title, col_btn = st.columns([6, 1])
with col_title:
    st.markdown("<h1>STRATEGY CLOUD <span style='color:#8B949E;font-size:0.8rem;font-weight:400'>/ Terminal</span></h1>", unsafe_allow_html=True)
with col_btn:
    st.write("")
    if st.button("REFRESH"):
        load_dashboard_data.clear()
        st.rerun()

# ── Настройки ──
with st.sidebar:
    st.markdown("### Configuration")
    days_back = st.slider("Dashboard lookback (visual, days)", 1, 90, ALLOC_DAYS)
    st.caption(f"Только для просмотра. Strategy Tree / Wheel всегда считают по фикс. периоду аллокации: {ALLOC_DAYS} дн. (config).")
    st.caption("Auto-refresh: 30s")

# ── Загрузка данных ──
data = load_dashboard_data(days_back)
# Окно периода аллокации (жёсткое) — его используют Strategy Tree и Wheel.
data_alloc = load_dashboard_data(ALLOC_DAYS)
if data_alloc is None:
    data_alloc = data  # страховка: если окно аллокации не загрузилось, не падаем

# ── Табы ──
tab_overview, tab_risk, tab_strategies, tab_3d, tab_surface, tab_tree, tab_steering, tab_pipeline = st.tabs([
    "Overview",
    "Risk",
    "Strategies",
    "3D Landscape",
    "3D Surface",
    "Strategy Tree",
    "Steering Wheel",
    "Pipeline",
])


# ═══════════════════════════════════════════════════════════════
#  OVERVIEW
# ═══════════════════════════════════════════════════════════════
with tab_overview:
    if not data:
        st.warning("No data. Ensure MT5 terminal is running.")
        st.stop()

    col1, col2, col3 = st.columns(3)
    updated = datetime.fromisoformat(data['updated']).strftime('%H:%M:%S')

    with col1:
        st.metric("Balance", f"{data['balance']:,.0f} RUB")
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
        <div style="padding: 1rem 0;">
            <div style="font-size: 0.75rem; text-transform: uppercase;
                        letter-spacing: 0.08em; color: {COL_MUTED};
                        margin-bottom: 0.3rem;">P&L Today</div>
            <div style="font-size: 1.5rem; font-weight: 600;
                        font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
                        color: {pnl_color};">{today_pnl:+,.1f} RUB</div>
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
            st.metric("Forecast P&L (30D)", f"{forecast_pnl:,.1f} RUB",
                      delta_color="normal")
        else:
            st.metric("Forecast P&L (30D)", "—")

    st.caption(f"Last update: {updated} | Trades ({days_back}D): {data['total_trades']}")

    # ── Volume + Equity Curve ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        col_vol, col_eq = st.columns(2)

        with col_vol:
            st.markdown("### Daily Volume")
            df_daily = data['trades_df'].copy()
            df_daily['date'] = df_daily['timestamp'].dt.date
            daily_stats = df_daily.groupby('date').agg(
                volume=('volume', 'sum'),
                trades=('profit_net', 'count'),
            ).reset_index()

            fig_vol = go.Figure()
            fig_vol.add_trace(go.Bar(
                x=daily_stats['date'], y=daily_stats['volume'],
                name='Volume (lots)', marker_color=COL_BLUE, opacity=0.7,
            ))
            fig_vol.add_trace(go.Scatter(
                x=daily_stats['date'], y=daily_stats['trades'],
                name='Trades', mode='lines+markers',
                line=dict(color=COL_AMBER, width=1.5),
                yaxis='y2',
            ))
            fig_vol.update_layout(
                yaxis=dict(title='Volume', side='left'),
                yaxis2=dict(title='Trades', side='right', overlaying='y'),
                legend=dict(orientation='h', y=1.12, x=0),
                bargap=0.15,
            )
            st.plotly_chart(plotly_dark_layout(fig_vol, 260), use_container_width=True,
                           key="overview_daily_volume")

        with col_eq:
            st.markdown("### Equity Curve")
            df_eq = data['trades_df'].sort_values('timestamp').copy()
            df_eq['cum_pnl'] = df_eq['profit_net'].cumsum()

            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(
                x=df_eq['timestamp'], y=df_eq['cum_pnl'],
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
                hovertemplate='Time: %{x}<br>Cum P&L: %{y:,.1f}<extra></extra>',
                name='',
            ))
            fig_eq.add_hline(y=0, line_dash='dot', line_color=COL_MUTED, opacity=0.4)
            st.plotly_chart(plotly_dark_layout(fig_eq, 260), use_container_width=True,
                           key="overview_equity_curve")

    # ── Trade scatter ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        st.markdown("### Trade Scatter")
        df_sorted = data['trades_df'].sort_values('timestamp').copy()
        colors = [COL_GREEN_LT if x >= 0 else COL_RED_LT for x in df_sorted['profit_net']]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_sorted['timestamp'], y=df_sorted['profit_net'],
            mode='markers',
            marker=dict(size=6, color=colors, line=dict(width=0.5, color=COL_PANEL),
                        symbol='diamond'),
            text=df_sorted.apply(
                lambda r: f"{r['symbol']} | PnL: {r['profit_net']:+.2f} | Vol: {r.get('volume', 0):.2f}",
                axis=1),
            hoverinfo='text', name='',
        ))
        fig.add_hline(y=0, line_dash='dot', line_color=COL_MUTED, opacity=0.4)
        fig.update_layout(hovermode='x unified')
        st.plotly_chart(plotly_dark_layout(fig, 380), use_container_width=True,
                       key="overview_trade_scatter")


# ═══════════════════════════════════════════════════════════════
#  RISK
# ═══════════════════════════════════════════════════════════════
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

        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            st.metric("Open Positions", f"{n_positions}")
        with col_r2:
            st.metric("Unrealized P&L", f"{unrealized_pnl:+,.1f} RUB",
                      delta_color="inverse")
        with col_r3:
            st.metric("Max Risk (SL)", f"{max_loss:,.1f} RUB")

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
                bargap=0.15,
            )
            st.plotly_chart(plotly_dark_layout(fig_risk, max(200, len(df_risk) * 30 + 60)),
                           use_container_width=True, key="risk_by_symbol")

        caption = f"Open: {n_positions} | Volume: {total_volume:.2f} lots | Budget: {quota:,.0f} RUB"
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
            st.metric("Open Positions (from strategies)", f"{n}")
            st.metric("Total Volume", f"{total_lot:.2f} lots")
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
    st.markdown("### Active Strategies")
    if data['active_strategies']:
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
        st.info("No active strategies.")

    # ── Trade log ──
    st.markdown("### Trade Log — Last 50")
    if not data['trades_df'].empty:
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
        st.info("No trades in history for selected period.")


# ═══════════════════════════════════════════════════════════════
#  3D LANDSCAPE
# ═══════════════════════════════════════════════════════════════
with tab_3d:
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
#  3D SURFACE
# ═══════════════════════════════════════════════════════════════
with tab_surface:
    st.markdown("### Parametric Surface — 3D")

    if not data:
        st.warning("No data.")
        st.stop()

    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        df_surf_src = data['trades_df'].copy()
        families = sorted(df_surf_src['strategy_type'].unique())
        sel_family = st.selectbox("Strategy family", families, key="surface_family")
        df_fam = df_surf_src[df_surf_src['strategy_type'] == sel_family].copy()

        if df_fam.empty:
            st.info("No data for selected family.")
        else:
            df_agg = df_fam.groupby(['symbol', 'param_key']).agg(
                pnl=('profit_net', 'sum'), trades=('profit_net', 'count'),
                wins=('profit_net', lambda x: (x > 0).sum()),
                volatility=('profit_net', 'std'), avg_pnl=('profit_net', 'mean'),
            ).reset_index()
            df_agg['win_rate'] = df_agg['wins'] / df_agg['trades'] * 100
            df_agg['volatility'] = df_agg['volatility'].fillna(0)

            def extract_numbers(key):
                return [float(x) for x in re.findall(r'[-+]?\d*\.?\d+', str(key))]

            sample_nums = extract_numbers(df_agg['param_key'].iloc[0]) if len(df_agg) > 0 else []

            col_ax1, col_ax2, col_z = st.columns(3)
            axis_options = {
                'trades': 'Trade count', 'win_rate': 'Win Rate (%)',
                'volatility': 'Volatility', 'avg_pnl': 'Avg P&L', 'pnl': 'Total P&L',
            }
            param_axis_options = {}
            if len(sample_nums) >= 1:
                param_axis_options['param_0'] = 'Param 1 (from key)'
            if len(sample_nums) >= 2:
                param_axis_options['param_1'] = 'Param 2 (from key)'

            all_x_options = {**param_axis_options, **axis_options}
            all_y_options = {**param_axis_options, **axis_options}
            z_options = {'pnl': 'Total P&L', 'avg_pnl': 'Avg P&L', 'win_rate': 'Win Rate (%)'}

            with col_ax1:
                x_axis = st.selectbox("X axis", list(all_x_options.keys()),
                                      format_func=lambda k: all_x_options[k], key="surf_x")
            with col_ax2:
                y_axis = st.selectbox("Y axis", list(all_y_options.keys()),
                                      format_func=lambda k: all_y_options[k],
                                      key="surf_y", index=min(1, len(all_y_options) - 1))
            with col_z:
                z_axis = st.selectbox("Z axis (height)", list(z_options.keys()),
                                      format_func=lambda k: z_options[k], key="surf_z")

            def get_axis_values(df, axis):
                if axis.startswith('param_'):
                    idx = int(axis.split('_')[1])
                    nums_list = df['param_key'].apply(lambda k: extract_numbers(k))
                    return nums_list.apply(lambda nums: nums[idx] if len(nums) > idx else 0.0).values
                return df[axis].values

            x_vals = get_axis_values(df_agg, x_axis)
            y_vals = get_axis_values(df_agg, y_axis)
            z_vals = df_agg[z_axis].values
            labels = df_agg['symbol'].str.replace('rfd', '') + ' | ' + df_agg['param_key']
            n_points = len(df_agg)

            if n_points < 3:
                st.warning("Insufficient data points (minimum 3 required).")
            else:
                x_unique = np.unique(x_vals)
                y_unique = np.unique(y_vals)
                use_surface = (len(x_unique) >= 2 and len(y_unique) >= 2 and
                               len(x_unique) * len(y_unique) <= n_points * 2)

                if use_surface:
                    from scipy.interpolate import griddata
                    xi = np.linspace(x_vals.min(), x_vals.max(), max(len(x_unique), 20))
                    yi = np.linspace(y_vals.min(), y_vals.max(), max(len(y_unique), 20))
                    X_grid, Y_grid = np.meshgrid(xi, yi)
                    Z_grid = griddata((x_vals, y_vals), z_vals, (X_grid, Y_grid), method='linear')
                    mask = np.isnan(Z_grid)
                    if mask.any():
                        Z_nearest = griddata((x_vals, y_vals), z_vals, (X_grid, Y_grid), method='nearest')
                        Z_grid[mask] = Z_nearest[mask]

                    fig_surf = go.Figure()
                    fig_surf.add_trace(go.Surface(
                        x=xi, y=yi, z=Z_grid,
                        colorscale=[[0, '#DA3633'], [0.5, '#161B22'], [1, '#2EA043']],
                        contours={"z": {"show": True, "usecolormap": True,
                                        "highlightcolor": "#ffffff", "project": {"z": True}}},
                        colorbar=dict(title=z_options[z_axis], x=1.02,
                                      tickfont=dict(size=16, color=COL_MUTED),
                                      title_font=dict(size=16)),
                        hovertemplate=f'{all_x_options[x_axis]}: %{{x:.1f}}<br>{all_y_options[y_axis]}: %{{y:.1f}}<br>{z_options[z_axis]}: %{{z:,.1f}}<extra></extra>',
                        name='',
                    ))
                    fig_surf.update_layout(
                        scene=dict(
                            xaxis=dict(title=all_x_options[x_axis], backgroundcolor=COL_PANEL,
                                       gridcolor=COL_GRID, tickfont=dict(size=16, color=COL_MUTED),
                                       title_font=dict(size=18)),
                            yaxis=dict(title=all_y_options[y_axis], backgroundcolor=COL_PANEL,
                                       gridcolor=COL_GRID, tickfont=dict(size=16, color=COL_MUTED),
                                       title_font=dict(size=18)),
                            zaxis=dict(title=z_options[z_axis], backgroundcolor=COL_PANEL,
                                       gridcolor=COL_GRID, tickfont=dict(size=16, color=COL_MUTED),
                                       title_font=dict(size=18)),
                            camera=dict(eye=dict(x=1.8, y=1.8, z=0.6)),
                        ),
                        paper_bgcolor=COL_PANEL, height=650,
                        margin=dict(l=0, r=0, t=10, b=0),
                        font=dict(color=COL_TEXT, size=16),
                    )
                    st.plotly_chart(fig_surf, use_container_width=True, key="3d_surface")
                    st.caption(f"Interpolated {n_points} points onto {len(xi)}x{len(yi)} grid. Ridges = profitable zones.")
                else:
                    st.info(f"Insufficient grid for surface ({n_points} points). Showing triangulated mesh.")

                    fig_mesh = go.Figure()
                    fig_mesh.add_trace(go.Mesh3d(
                        x=x_vals, y=y_vals, z=z_vals,
                        colorscale=[[0, '#DA3633'], [0.5, '#161B22'], [1, '#2EA043']],
                        intensity=z_vals,
                        colorbar=dict(title=z_options[z_axis], x=1.02,
                                      tickfont=dict(size=16, color=COL_MUTED),
                                      title_font=dict(size=16)),
                        hovertemplate=f'{all_x_options[x_axis]}: %{{x:.1f}}<br>{all_y_options[y_axis]}: %{{y:.1f}}<br>{z_options[z_axis]}: %{{z:,.1f}}<extra></extra>',
                        name='',
                    ))
                    fig_mesh.add_trace(go.Scatter3d(
                        x=x_vals, y=y_vals, z=z_vals, mode='markers+text',
                        marker=dict(size=4, color=COL_TEXT, line=dict(width=0.5, color=COL_PANEL)),
                        text=labels, textposition='top center',
                        textfont=dict(size=12, color=COL_MUTED),
                        hoverinfo='skip', name='',
                    ))
                    fig_mesh.update_layout(
                        scene=dict(
                            xaxis=dict(title=all_x_options[x_axis], backgroundcolor=COL_PANEL,
                                       gridcolor=COL_GRID, tickfont=dict(size=16, color=COL_MUTED),
                                       title_font=dict(size=18)),
                            yaxis=dict(title=all_y_options[y_axis], backgroundcolor=COL_PANEL,
                                       gridcolor=COL_GRID, tickfont=dict(size=16, color=COL_MUTED),
                                       title_font=dict(size=18)),
                            zaxis=dict(title=z_options[z_axis], backgroundcolor=COL_PANEL,
                                       gridcolor=COL_GRID, tickfont=dict(size=16, color=COL_MUTED),
                                       title_font=dict(size=18)),
                            camera=dict(eye=dict(x=1.8, y=1.8, z=0.6)),
                        ),
                        paper_bgcolor=COL_PANEL, height=650,
                        margin=dict(l=0, r=0, t=10, b=0),
                        font=dict(color=COL_TEXT, size=16),
                        showlegend=False,
                    )
                    st.plotly_chart(fig_mesh, use_container_width=True, key="3d_mesh")

            with st.expander("Source data"):
                display_df = df_agg[['symbol', 'param_key', 'pnl', 'trades',
                                     'win_rate', 'volatility', 'avg_pnl']].copy()
                display_df['symbol'] = display_df['symbol'].str.replace('rfd', '')
                st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No data for surface.")

    st.markdown("---")
    st.caption("Select a family, set X/Y to parameter axes, Z to P&L. Ridges indicate optimal parameter zones.")



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
    st.markdown("### Strategy Tree")
    st.caption(f"Allocation period: {ALLOC_DAYS} дн. (config.SteeringParams.lookback_days) — это окно, по которому реально распределяется объём в Wheel.")
    if days_back != ALLOC_DAYS:
        st.info(f"⚠ Слайдер показывает {days_back} дн., но дерево аллокации всегда {ALLOC_DAYS} дн. Ниже — окно реальной перекладки объёма (синхрон с Wheel).")

    if not data:
        st.warning("No data.")
        st.stop()

    trades_df = data_alloc.get('trades_df')
    if trades_df is None or trades_df.empty or not PLOTLY_AVAILABLE:
        if not PLOTLY_AVAILABLE:
            st.warning("Plotly недоступен — Strategy Tree не может быть построен.")
            st.stop()
        _ds = data_alloc.get('dash_stats') or {}
        st.info(
            "**Дерево пустое.** Оно строится только из **закрытых** позиций наших стратегий "
            "(magic 770000–869999, символы `*rfd`) за период аллокации (config.lookback_days).\n\n"
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





    # ── Объём: всего / средний недельный темп прироста (week-over-week) ──
    # Слева — суммарный объём за всё окно (закрытые позиции), справа — средний
    # недельный темп прироста объёма, %.
    df_tree['volume'] = pd.to_numeric(df_tree['volume'], errors='coerce').fillna(0.0)
    _ts_col = 'timestamp' if 'timestamp' in df_tree.columns else 'time'
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
    _max_abs = max(1.0, max(abs(p) for p in pnls))
    node_colors = []
    for _p in pnls:
        if _p >= 0:
            _r = _p / _max_abs
            node_colors.append(
                f'rgb({int(46 + 26 * _r)}, {int(150 + 35 * _r)}, {int(67 + 26 * _r)})'
            )
        else:
            _r = -_p / _max_abs
            node_colors.append(
                f'rgb({int(218 + 25 * _r)}, {int(54 + 30 * _r)}, {int(51 + 20 * _r)})'
            )

    # ── Treemap ────────────────────────────────────────────────
    fig_tree = go.Figure(go.Treemap(
        ids=ids,
        parents=parents,
        labels=labels,
        values=values,
        branchvalues='remainder',
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

    # ИСПРАВЛЕНО: use_container_width -> width='stretch'
    st.plotly_chart(fig_tree, width='stretch', key="strategy_tree")

    with st.expander("Reading the tree"):
        st.markdown("""
        | Level | Shown |
        |-------|-------|
        | Total | Net PnL of all closed trades in the period |
        | Family | Strategy family (RF, LogReg, MA, ...) |
        | Symbol | Family x symbol |
        | Strategy | Top‑3 param_key by PnL + "Others" bucket |

        **Size** — |PnL| (node area). **Color** — PnL gradient: green = profit, red = loss.
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

    st.markdown("###Wheel — Quota by Family")
    st.caption(f"Allocation period: {ALLOC_DAYS} дн. (config) — то же окно, что и Strategy Tree. Квоты = ранг по прибыли дерева (лидер → максимум).")
    st.caption("Категория = «символ + семейство» (например EUR - parabolic). "
               "Квоты считаются по реальным закрытым сделкам (entry='out').")

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
                if 'type' not in df_active.columns:
                    df_active['type'] = df_active['param_key'].astype(str)
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

            # min_trades для скоринга берётся из config.SteeringParams (сейчас 2)

            new_quotas = calculate_steering_wheel_quotas(
                strategies_data,
                current_quotas,
                {
                    'alpha': steering_cfg.alpha,
                    'min_q': steering_cfg.min_q,
                    'max_q': steering_cfg.max_q,
                    'score_mode': steering_cfg.score_mode,
                    'gamma': getattr(steering_cfg, 'gamma', 1.5),
                }
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
            # Ранг по прибыли дерева должен совпадать с рангом доли штурвала.
            _sync = df_sw[['name', 'family', 'pnl', 'trades', 'current_quota', 'new_quota']].copy()
            _sync = _sync.sort_values('pnl', ascending=False).reset_index(drop=True)
            _sync.insert(0, 'PnL rank', range(1, len(_sync) + 1))
            _sync['Q rank'] = _sync['new_quota'].rank(ascending=False, method='min').astype(int)
            st.markdown("#### Sync: Strategy Tree → Wheel")
            st.caption(f"Ранг прибыли дерева (PnL rank) ↔ ранг доли штурвала (Q rank). "
                       f"Окно аллокации: {ALLOC_DAYS} дн. Лидер по прибыли должен получать максимальную долю "
                       "(кроме ограничения пол/потолок из config).")
            _sdisp = _sync.copy()
            _sdisp['Tree PnL'] = _sdisp['pnl'].round(0).astype(int)
            _sdisp['Cur Q %'] = (_sdisp['current_quota'] * 100).round(1)
            _sdisp['New Q %'] = (_sdisp['new_quota'] * 100).round(1)
            st.dataframe(
                _sdisp[['PnL rank', 'name', 'Tree PnL', 'trades', 'Cur Q %', 'New Q %', 'Q rank']],
                use_container_width=True, hide_index=True)


            df_sw = df_sw.sort_values('delta', ascending=False).reset_index(drop=True)
            n_delta = int((df_sw['delta'].abs() > 1e-4).sum())
            st.caption(f"Категорий (символ+семейство): {len(df_sw)} | с Δ ≠ 0: {n_delta} | параметры из config.SteeringParams (α={steering_cfg.alpha}, мин.сделок={steering_cfg.min_trades}, пол={steering_cfg.min_q}, потолок={steering_cfg.max_q}, скоринг={steering_cfg.score_mode})")

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
                f"Окно аллокации: {ALLOC_DAYS} дн. · скоринг: {steering_cfg.score_mode} (вес по прибыли за окно, как в Strategy Tree). "
                "Категории без сделок за окно получают минимум (объём уходит в зелёные зоны дерева). "
                "enabled=False — лоты не меняются, расчёт индикативный."
            )

    else:
        st.info("Нет данных для работы штурвала.")



# ═══════════════════════════════════════════════════════════════
#  PIPELINE
# ═══════════════════════════════════════════════════════════════
with tab_pipeline:
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
