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

st.set_page_config(page_title="Strategy Cloud", layout="wide")


@st.cache_data(ttl=30)
def load_dashboard_data(days_back=30):
    """Единая точка входа — все данные для дэшборда из daily_report.py"""
    return get_dashboard_data(days_back)


def make_gradient_colors(values, positive_hex='#26A69A', negative_hex='#EF5350'):
    """Возвращает список цветов с насыщенностью, пропорциональной величине PnL."""
    if not values:
        return []
    abs_vals = [abs(v) for v in values]
    max_abs = max(abs_vals) if max(abs_vals) > 0 else 1

    def hex_to_rgb(h):
        h = h.lstrip('#')
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    pos_base = hex_to_rgb(positive_hex)
    pos_light = (232, 245, 243)
    neg_base = hex_to_rgb(negative_hex)
    neg_light = (252, 232, 232)

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


def make_empty_placeholder(title, description, icon="🔬"):
    """Заглушка для будущего графика."""
    st.markdown(f"### {icon} {title}")
    st.info(description)
    st.markdown("---")


# ── Заголовок + кнопка обновления ──
col_title, col_btn = st.columns([5, 1])
with col_title:
    st.title("📊 Рэнкинг стратегий")
with col_btn:
    st.write("")
    if st.button("🔄 Обновить"):
        load_dashboard_data.clear()
        st.rerun()

# ── Настройки ──
with st.sidebar:
    st.subheader("Настройки")
    days_back = st.slider("История сделок (дней)", 1, 90, 30)
    st.caption("Данные обновляются каждые 30 секунд")

# ── Загрузка данных ──
data = load_dashboard_data(days_back)

# ── Табы ──
tab_overview, tab_risk, tab_strategies, tab_3d, tab_surface, tab_roadmap = st.tabs([
    "📊 Обзор",
    "🎯 Риск",
    "📋 Стратегии",
    "🗺️ 3D Ландшафт",
    "🏔️ 3D Поверхность",
    "🚧 В разработке",
])


# ═══════════════════════════════════════════════════════════════
#  ТАБ: ОБЗОР
# ═══════════════════════════════════════════════════════════════
with tab_overview:
    if not data:
        st.warning("Не удалось загрузить данные. Убедитесь, что MT5 запущен.")
        st.stop()

    # ── Сводка ──
    col1, col2, col3 = st.columns(3)
    updated = datetime.fromisoformat(data['updated']).strftime('%H:%M:%S')

    with col1:
        st.metric("Баланс", f"{data['balance']:,.0f} руб")
    with col2:
        st.metric("Квота риска", f"{data['quota']:,.0f} руб")
    with col3:
        forecast_pnl = None
        if not data['trades_df'].empty:
            daily_avg = data['trades_df'].groupby(
                data['trades_df']['timestamp'].dt.date
            )['profit_net'].sum().mean()
            if pd.notna(daily_avg):
                forecast_pnl = daily_avg * 21
        if forecast_pnl is not None:
            st.metric("Прогноз PnL (мес)", f"{forecast_pnl:,.1f} руб",
                      delta_color="normal")
        else:
            st.metric("Прогноз PnL (мес)", "Нет данных")

    st.caption(f"Обновлено: {updated} | Сделок за {days_back} дн.: {data['total_trades']}")

    # ── Дневной объём + Equity Curve ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        col_vol, col_eq = st.columns(2)

        with col_vol:
            st.subheader("📦 Дневной объём торгов")
            df_daily = data['trades_df'].copy()
            df_daily['date'] = df_daily['timestamp'].dt.date
            daily_stats = df_daily.groupby('date').agg(
                volume=('volume', 'sum'),
                trades=('profit_net', 'count'),
                pnl=('profit_net', 'sum'),
            ).reset_index()

            fig_vol = go.Figure()
            fig_vol.add_trace(go.Bar(
                x=daily_stats['date'],
                y=daily_stats['volume'],
                name='Объём (лот)',
                marker_color='#90CAF9',
                yaxis='y',
            ))
            fig_vol.add_trace(go.Scatter(
                x=daily_stats['date'],
                y=daily_stats['trades'],
                name='Сделок',
                mode='lines+markers',
                line=dict(color='#1565C0', width=2),
                yaxis='y2',
            ))
            fig_vol.update_layout(
                height=260,
                template='plotly_white',
                margin=dict(l=40, r=40, t=10, b=30),
                xaxis_title='Дата',
                yaxis=dict(title='Объём (лот)', side='left'),
                yaxis2=dict(title='Сделок', side='right', overlaying='y'),
                showlegend=True,
                legend=dict(orientation='h', y=1.12, x=0),
                bargap=0.2,
            )
            st.plotly_chart(fig_vol, use_container_width=True)

        with col_eq:
            st.subheader("📈 Equity Curve")
            df_eq = data['trades_df'].sort_values('timestamp').copy()
            df_eq['cum_pnl'] = df_eq['profit_net'].cumsum()

            fig_eq = go.Figure()
            fig_eq.add_trace(go.Scatter(
                x=df_eq['timestamp'],
                y=df_eq['cum_pnl'],
                mode='lines',
                line=dict(color='#26A69A', width=2),
                fill='tozeroy',
                fillgradient=dict(
                    type='vertical',
                    colorscale=[
                        [0, 'rgba(239, 83, 80, 0.3)'],
                        [0.5, 'rgba(239, 83, 80, 0.05)'],
                        [0.5, 'rgba(38, 166, 154, 0.05)'],
                        [1, 'rgba(38, 166, 154, 0.3)'],
                    ],
                ),
                hovertemplate='Время: %{x}<br>Кум. PnL: %{y:,.1f} руб<extra></extra>',
                name='',
            ))
            fig_eq.add_hline(y=0, line_dash='dash', line_color='gray', opacity=0.5)
            fig_eq.update_layout(
                height=260,
                template='plotly_white',
                margin=dict(l=50, r=20, t=10, b=30),
                xaxis_title='Время',
                yaxis_title='Кум. PnL (руб)',
                showlegend=False,
            )
            st.plotly_chart(fig_eq, use_container_width=True)

    # ── Облако сделок ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        st.subheader("☁️ Облако сделок")
        df_sorted = data['trades_df'].sort_values('timestamp').copy()
        colors = ['#26A69A' if x >= 0 else '#EF5350' for x in df_sorted['profit_net']]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_sorted['timestamp'],
            y=df_sorted['profit_net'],
            mode='markers',
            marker=dict(
                size=10,
                color=colors,
                line=dict(width=1, color='white'),
                symbol='diamond'
            ),
            text=df_sorted.apply(
                lambda r: f"{r['symbol']}<br>{r['entry']}<br>PnL: {r['profit_net']:+.2f}<br>Vol: {r.get('volume', 0):.2f}",
                axis=1
            ),
            hoverinfo='text',
            name='Сделки'
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        fig.update_layout(
            height=400,
            xaxis_title="Время",
            yaxis_title="PnL (руб)",
            hovermode="x unified",
            showlegend=False,
            template="plotly_white",
            margin=dict(l=60, r=20, t=30, b=40)
        )
        fig.update_xaxes(dtick="D")
        st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
#  ТАБ: РИСК
# ═══════════════════════════════════════════════════════════════
with tab_risk:
    if not data:
        st.warning("Нет данных.")
        st.stop()

    st.subheader("🎯 Использование квоты риска")
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
                risk_by_symbol[sym] = {
                    'count': 0, 'volume': 0.0, 'pnl': 0.0, 'max_loss': 0.0,
                }
            risk_by_symbol[sym]['count'] += 1
            risk_by_symbol[sym]['volume'] += p.volume
            risk_by_symbol[sym]['pnl'] += p.profit
            risk_by_symbol[sym]['max_loss'] += sl_loss

        risk_pct = (max_loss / quota * 100) if quota > 0 else 0

        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        with col_r1:
            st.metric("Открыто позиций", f"{n_positions}")
        with col_r2:
            st.metric("Нереализ. PnL", f"{unrealized_pnl:+,.1f} руб",
                      delta_color="inverse")
        with col_r3:
            st.metric("Макс. риск (SL)", f"{max_loss:,.1f} руб")
        with col_r4:
            st.metric("Квота использована", f"{risk_pct:.1f}%",
                      delta_color="inverse")

        fig_gauge = go.Figure()
        fig_gauge.add_trace(go.Indicator(
            mode="gauge+number",
            value=risk_pct,
            number={'suffix': '%', 'font': {'size': 28}},
            gauge={
                'axis': {'range': [0, 150], 'tickwidth': 1},
                'bar': {'color': "#1a1a1a"},
                'steps': [
                    {'range': [0, 30], 'color': "#26A69A"},
                    {'range': [30, 70], 'color': "#FFD54F"},
                    {'range': [70, 150], 'color': "#EF5350"},
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.85,
                    'value': 100,
                },
            },
        ))
        fig_gauge.update_layout(
            height=220, template='plotly_white',
            margin=dict(l=40, r=40, t=10, b=10),
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

        if risk_by_symbol:
            df_risk = pd.DataFrame([
                {'symbol': s, **v} for s, v in risk_by_symbol.items()
            ]).sort_values('max_loss', ascending=True)
            df_risk['display_sym'] = df_risk['symbol']
            risk_colors = make_gradient_colors([-x for x in df_risk['max_loss']])

            fig_risk = go.Figure()
            fig_risk.add_trace(go.Bar(
                x=df_risk['max_loss'],
                y=df_risk['display_sym'],
                orientation='h',
                marker_color=risk_colors,
                text=df_risk['count'],
                textposition='outside',
                texttemplate='%{text}',
                hovertemplate=(
                    '<b>%{y}</b><br>Макс. риск: %{x:,.1f} руб<br>'
                    'Позиций: %{text}<extra></extra>'
                ),
                name='',
            ))
            fig_risk.update_layout(
                height=max(200, len(df_risk) * 30 + 60),
                xaxis_title='Макс. риск по SL (руб)',
                yaxis_title='', showlegend=False,
                template='plotly_white',
                margin=dict(l=80, r=60, t=10, b=40), bargap=0.2,
            )
            st.plotly_chart(fig_risk, use_container_width=True)
            st.caption("Числа на столбцах — количество позиций")

        caption_parts = [
            f"Открыто: {n_positions} | Объём: {total_volume:.2f} лот | "
            f"Квота: {quota:,.0f} руб"
        ]
        if no_sl_count > 0:
            caption_parts.append(
                f"⚠️ {no_sl_count} поз. без SL — не учтены в макс. риске"
            )
        st.caption(" | ".join(caption_parts))

    elif positions is not None and len(positions) == 0:
        st.info("Нет открытых позиций — риск нулевой.")
    else:
        if data.get('active_strategies'):
            active = [s for s in data['active_strategies'] if s.get('has_position')]
            n = len(active)
            total_lot = sum(s.get('lot', 0) for s in active)
            st.metric("Открыто позиций (из стратегий)", f"{n}")
            st.metric("Суммарный объём", f"{total_lot:.2f} лот")
            st.caption(
                f"MT5 недоступен для детального риска. "
                f"Квота: {quota:,.0f} руб | "
                f"Активных стратегий с позицией: {n}"
            )
        else:
            st.info("Нет открытых позиций.")

    # ── Exposure heatmap ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        st.subheader("🔥 Exposure: сделки по символам во времени")
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
                [0.0, '#f5f5f5'],
                [0.33, '#81C784'],
                [0.66, '#FFB74D'],
                [1.0, '#E53935'],
            ],
            zmin=0, zmax=z_max,
            text=pivot.values, texttemplate='%{text}',
            textfont=dict(size=10),
            hovertemplate='Символ: %{y}<br>Время: %{x}<br>Сделок: %{z}<extra></extra>',
        ))
        fig_heat.update_layout(
            height=350, xaxis_title='Время', yaxis_title='Символ',
            template='plotly_white',
            margin=dict(l=80, r=20, t=20, b=60),
            xaxis=dict(tickangle=-45),
        )
        st.plotly_chart(fig_heat, use_container_width=True)
        st.caption("Цвет: 0 сделок — серый, 1–2 — зелёный, 3 (лимит) — оранжевый, >3 — красный (баг)")


# ═══════════════════════════════════════════════════════════════
#  ТАБ: СТРАТЕГИИ
# ═══════════════════════════════════════════════════════════════
with tab_strategies:
    if not data:
        st.warning("Нет данных.")
        st.stop()

    # ── PnL по стратегиям ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        st.subheader("📊 PnL по стратегиям")
        df_strat = data['trades_df'].groupby(
            ['symbol', 'strategy_type', 'param_key']
        ).agg(
            pnl=('profit_net', 'sum'),
            trades=('profit_net', 'count'),
        ).reset_index()
        df_strat['name'] = (
            df_strat['symbol'].str.replace('rfd', '') + ' | ' +
            df_strat['strategy_type'] + ' | ' +
            df_strat['param_key']
        )
        df_strat = df_strat.sort_values('pnl', ascending=True).reset_index(drop=True)
        colors_strat = make_gradient_colors(df_strat['pnl'].tolist())

        fig1 = go.Figure()
        fig1.add_trace(go.Bar(
            x=df_strat['pnl'], y=df_strat['name'],
            orientation='h', marker_color=colors_strat,
            text=df_strat['trades'], textposition='outside',
            texttemplate='%{text}',
            hovertemplate='<b>%{y}</b><br>PnL: %{x:,.1f} руб<br>Сделок: %{text}<extra></extra>',
            name='',
        ))
        fig1.update_layout(
            height=max(450, len(df_strat) * 24),
            xaxis_title='PnL (руб)', yaxis_title='',
            showlegend=False, template='plotly_white',
            margin=dict(l=20, r=80, t=20, b=40), bargap=0.15,
        )
        st.plotly_chart(fig1, use_container_width=True)
        st.caption("Числа на столбцах — количество сделок за период")

    # ── Win Rate и Profit Factor ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        st.subheader("📊 Win Rate и Profit Factor по семействам")
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
            if r['gross_loss'] > 0 else float('inf'),
            axis=1,
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
                hovertemplate='<b>%{y}</b><br>Win Rate: %{text}%<extra></extra>',
                name='',
            ))
            fig_wr.update_layout(
                height=max(250, len(df_wr_sorted) * 30 + 40),
                xaxis_title='Win Rate (%)', yaxis_title='',
                showlegend=False, template='plotly_white',
                margin=dict(l=20, r=60, t=10, b=30), bargap=0.2,
            )
            st.plotly_chart(fig_wr, use_container_width=True)

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
            fig_pf.add_hline(y=1.0, line_dash='dash', line_color='red', opacity=0.6)
            fig_pf.update_layout(
                height=max(250, len(df_pf_sorted) * 30 + 40),
                xaxis_title='Семейство', yaxis_title='Profit Factor',
                showlegend=False, template='plotly_white',
                margin=dict(l=50, r=20, t=10, b=60), bargap=0.25,
                xaxis={'categoryorder': 'total ascending'},
            )
            st.plotly_chart(fig_pf, use_container_width=True)

        st.caption("Красная пунктирная линия на PF = 1.0 — граница безубытка")

    # ── PnL по семействам ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        st.subheader("📊 PnL по семействам стратегий")
        df_fam = data['trades_df'].groupby('strategy_type').agg(
            pnl=('profit_net', 'sum'),
            trades=('profit_net', 'count'),
        ).reset_index()
        df_fam = df_fam.sort_values('pnl', ascending=True).reset_index(drop=True)
        colors_fam = make_gradient_colors(df_fam['pnl'].tolist())

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df_fam['strategy_type'], y=df_fam['pnl'],
            marker_color=colors_fam,
            text=df_fam['trades'], textposition='outside',
            texttemplate='%{text}',
            hovertemplate='<b>%{x}</b><br>PnL: %{y:,.1f} руб<br>Сделок: %{text}<extra></extra>',
            name='',
        ))
        fig2.add_hline(y=0, line_dash='dash', line_color='gray', opacity=0.5)
        fig2.update_layout(
            height=400, xaxis_title='Семейство стратегий',
            yaxis_title='PnL (руб)', showlegend=False,
            template='plotly_white',
            margin=dict(l=60, r=20, t=20, b=60), bargap=0.25,
            xaxis={'categoryorder': 'total ascending'},
        )
        st.plotly_chart(fig2, use_container_width=True)
        st.caption("Числа на столбцах — количество сделок за период")

    # ── Торгующие стратегии ──
    st.subheader("Торгующие стратегии")
    if data['active_strategies']:
        df_active = pd.DataFrame(data['active_strategies'])
        df_active = df_active.sort_values('lot', ascending=False).reset_index(drop=True)
        df_active['статус'] = df_active['has_position'].apply(
            lambda x: '🟢 в позиции' if x else '⚪ ожидание'
        )
        display_cols = ['статус', 'symbol', 'type', 'param_key', 'lot', 'magic']
        cols_to_show = [c for c in display_cols if c in df_active.columns]
        st.dataframe(
            df_active[cols_to_show], use_container_width=True,
            column_config={
                'lot': st.column_config.NumberColumn(format="%.2f"),
                'magic': st.column_config.NumberColumn(format="%.0f"),
            }, hide_index=True,
        )

        st.subheader("Распределение по символам")
        by_symbol = df_active.groupby('symbol').agg(
            стратегий=('symbol', 'count'),
            лот=('lot', 'sum'),
            в_позиции=('has_position', 'sum'),
        ).reset_index()
        st.dataframe(by_symbol, use_container_width=True, hide_index=True)
    else:
        st.info("Нет активных стратегий.")

    # ── Журнал сделок ──
    st.subheader("Журнал сделок (последние 50)")
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
        st.info("Нет сделок в истории MT5 за выбранный период.")


# ═══════════════════════════════════════════════════════════════
#  ТАБ: 3D ЛАНДШАФТ (пузыри)
# ═══════════════════════════════════════════════════════════════
with tab_3d:
    st.subheader("🗺️ 3D Ландшафт доходности стратегий")

    st.markdown("""
    **Концепция:** каждая стратегия — точка в 3D-пространстве.

    - **Ось X** — кумулятивный PnL стратегии (вправо = прибыль, влево = убыток)
    - **Ось Y** — волатильность доходности (разброс результатов)
    - **Ось Z** — количество сделок (высота столбика)
    - **Цвет** — Profit Factor (зелёный = прибыльная, красный = убыточная)
    - **Размер** — пропорционален количеству сделок

    Холсты, которые «тянут вниз» (большие красные столбы слева), — кандидаты на сокращение объёма.
    Холсты, которые «тянут вверх» (зелёные справа) — кандидаты на увеличение.
    """)

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

        df_3d['name'] = (
            df_3d['symbol'].str.replace('rfd', '') + '|' +
            df_3d['strategy_type']
        )
        df_3d['volatility'] = df_3d['volatility'].fillna(0)
        df_3d['profit_factor'] = df_3d.apply(
            lambda r: abs(r['wins'] / r['losses']) if r['losses'] > 0
            else (10.0 if r['wins'] > 0 else 0),
            axis=1,
        )

        # Цвет по PF
        pf_vals = df_3d['profit_factor'].clip(0, 3)
        colors_3d = []
        for pf in pf_vals:
            if pf >= 1.0:
                ratio = min((pf - 1.0) / 2.0, 1.0)
                colors_3d.append(f'rgb({int(200 - 162*ratio)}, {int(220 - 54*ratio)}, {int(154 - 0*ratio)})')
            else:
                ratio = min((1.0 - pf) / 1.0, 1.0)
                colors_3d.append(f'rgb({int(239)}, {int(83 + 70*ratio)}, {int(80)})')

        # Размер по trades
        sizes = df_3d['trades'].clip(lower=1) * 9

        fig_3d = go.Figure()
        fig_3d.add_trace(go.Scatter3d(
            x=df_3d['pnl'],
            y=df_3d['volatility'],
            z=df_3d['trades'],
            mode='markers+text',
            marker=dict(
                size=sizes,
                color=colors_3d,
                line=dict(width=1, color='white'),
                opacity=0.85,
            ),
            text=df_3d['name'],
            textposition='top center',
            textfont=dict(size=8),
            hovertemplate=(
                '<b>%{text}</b><br>'
                'PnL: %{x:,.1f} руб<br>'
                'Волатильность: %{y:,.1f}<br>'
                'Сделок: %{z}<extra></extra>'
            ),
            name='',
        ))

        # Нулевая плоскость
        fig_3d.add_trace(go.Scatter3d(
            x=[0, 0], y=[0, df_3d['volatility'].max() * 1.1 if df_3d['volatility'].max() > 0 else 1],
            z=[0, df_3d['trades'].max() * 1.1 if df_3d['trades'].max() > 0 else 1],
            mode='lines',
            line=dict(color='gray', width=2, dash='dash'),
            showlegend=False,
            hoverinfo='skip',
        ))

        fig_3d.update_layout(
            scene=dict(
                xaxis=dict(title='PnL (руб)', backgroundcolor='white',
                          gridcolor='#e0e0e0', showbackground=True),
                yaxis=dict(title='Волатильность', backgroundcolor='white',
                          gridcolor='#e0e0e0', showbackground=True),
                zaxis=dict(title='Сделок', backgroundcolor='white',
                          gridcolor='#e0e0e0', showbackground=True),
                camera=dict(eye=dict(x=1.5, y=1.5, z=0.8)),
            ),
            height=650,
            template='plotly_white',
            margin=dict(l=0, r=0, t=30, b=0),
            showlegend=False,
        )
        st.plotly_chart(fig_3d, use_container_width=True)

        st.caption(
            "Вращайте мышью. Зелёные точки справа — прибыльные стратегии, "
            "красные слева — убыточные. Высота = объём активности, "
            "глубина = волатильность."
        )

        # ── Легенда-пояснение ──
        with st.expander("📖 Как читать график"):
            st.markdown("""
            | Параметр | Ось | Что значит |
            |----------|-----|------------|
            | PnL | X (горизонталь) | Суммарный профит/убыток за период |
            | Волатильность | Y (глубина) | Разброс результатов сделок |
            | Сделок | Z (высота) | Активность стратегии |
            | Цвет | — | PF > 1 — зелёный, PF < 1 — красный |
            | Размер | — | Пропорционален количеству сделок |

            **Стратегии для увеличения лота:** зелёные, крупные, с низкой волатильностью (близко к нулю по Y).

            **Стратегии для сокращения:** красные, слева от нуля, с высокой волатильностью.

            **Стратегии под вопросом:** мелкие точки — мало сделок, статистика ненадёжна.
            """)

    else:
        st.info("Нет данных для построения 3D-модели.")


# ═══════════════════════════════════════════════════════════════
#  ТАБ: 3D ПОВЕРХНОСТЬ (параметрический ландшафт)
# ═══════════════════════════════════════════════════════════════
with tab_surface:
    st.subheader("🏔️ 3D Поверхность доходности")

    st.markdown("""
    **Режим полотна:** параметрический ландшафт одной семьи стратегий.

    Выбираешь семейство и два параметра — получаешь 3D-поверхность,
    где высота = суммарный PnL. «Хребты» — оптимальные зоны параметров,
    «долины» — убыточные комбинации.
    """)

    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        df_surf_src = data['trades_df'].copy()

        # ── Выбор семейства ──
        families = sorted(df_surf_src['strategy_type'].unique())
        sel_family = st.selectbox(
            "Семейство стратегий", families,
            key="surface_family"
        )

        df_fam = df_surf_src[df_surf_src['strategy_type'] == sel_family].copy()

        if df_fam.empty:
            st.info("Нет данных для выбранного семейства.")
        else:
            # ── Агрегация по (symbol, param_key) ──
            df_agg = df_fam.groupby(['symbol', 'param_key']).agg(
                pnl=('profit_net', 'sum'),
                trades=('profit_net', 'count'),
                wins=('profit_net', lambda x: (x > 0).sum()),
                volatility=('profit_net', 'std'),
                avg_pnl=('profit_net', 'mean'),
            ).reset_index()
            df_agg['win_rate'] = df_agg['wins'] / df_agg['trades'] * 100
            df_agg['volatility'] = df_agg['volatility'].fillna(0)

            # ── Попытка извлечь числовые параметры из param_key ──
            def extract_numbers(key):
                """Извлекает все числа из строки param_key."""
                return [float(x) for x in re.findall(r'[-+]?\d*\.?\d+', str(key))]

            sample_nums = extract_numbers(df_agg['param_key'].iloc[0]) if len(df_agg) > 0 else []

            # ── Выбор осей ──
            col_ax1, col_ax2, col_z = st.columns(3)

            axis_options = {
                'trades': 'Количество сделок',
                'win_rate': 'Win Rate (%)',
                'volatility': 'Волатильность',
                'avg_pnl': 'Средний PnL',
                'pnl': 'Суммарный PnL',
            }

            param_axis_options = {}
            if len(sample_nums) >= 1:
                param_axis_options['param_0'] = 'Параметр 1 (из param_key)'
            if len(sample_nums) >= 2:
                param_axis_options['param_1'] = 'Параметр 2 (из param_key)'

            all_x_options = {**param_axis_options, **axis_options}
            all_y_options = {**param_axis_options, **axis_options}
            z_options = {'pnl': 'Суммарный PnL', 'avg_pnl': 'Средний PnL', 'win_rate': 'Win Rate (%)'}

            with col_ax1:
                x_axis = st.selectbox("Ось X", list(all_x_options.keys()),
                                      format_func=lambda k: all_x_options[k],
                                      key="surf_x")
            with col_ax2:
                y_axis = st.selectbox("Ось Y", list(all_y_options.keys()),
                                      format_func=lambda k: all_y_options[k],
                                      key="surf_y",
                                      index=min(1, len(all_y_options) - 1))
            with col_z:
                z_axis = st.selectbox("Ось Z (высота)", list(z_options.keys()),
                                      format_func=lambda k: z_options[k],
                                      key="surf_z")

            # ── Извлечение значений ──
            def get_axis_values(df, axis):
                if axis.startswith('param_'):
                    idx = int(axis.split('_')[1])
                    nums_list = df['param_key'].apply(lambda k: extract_numbers(k))
                    return nums_list.apply(
                        lambda nums: nums[idx] if len(nums) > idx else 0.0
                    ).values
                return df[axis].values

            x_vals = get_axis_values(df_agg, x_axis)
            y_vals = get_axis_values(df_agg, y_axis)
            z_vals = df_agg[z_axis].values

            labels = (df_agg['symbol'].str.replace('rfd', '') +
                      ' | ' + df_agg['param_key'])

            n_points = len(df_agg)

            if n_points < 3:
                st.warning("Слишком мало точек для поверхности (нужно минимум 3).")
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

                    Z_grid = griddata(
                        (x_vals, y_vals), z_vals,
                        (X_grid, Y_grid), method='linear'
                    )
                    mask = np.isnan(Z_grid)
                    if mask.any():
                        Z_nearest = griddata(
                            (x_vals, y_vals), z_vals,
                            (X_grid, Y_grid), method='nearest'
                        )
                        Z_grid[mask] = Z_nearest[mask]

                    fig_surf = go.Figure()
                    fig_surf.add_trace(go.Surface(
                        x=xi, y=yi, z=Z_grid,
                        colorscale='RdYlGn',
                        contours={
                            "z": {
                                "show": True,
                                "usecolormap": True,
                                "highlightcolor": "#ffffff",
                                "project": {"z": True},
                            }
                        },
                        colorbar=dict(title=z_options[z_axis], x=1.02),
                        hovertemplate=(
                            f'{all_x_options[x_axis]}: %{{x:.1f}}<br>'
                            f'{all_y_options[y_axis]}: %{{y:.1f}}<br>'
                            f'{z_options[z_axis]}: %{{z:,.1f}}<extra></extra>'
                        ),
                        name='',
                    ))

                    fig_surf.update_layout(
                        scene=dict(
                            xaxis=dict(title=all_x_options[x_axis]),
                            yaxis=dict(title=all_y_options[y_axis]),
                            zaxis=dict(title=z_options[z_axis]),
                            camera=dict(eye=dict(x=1.8, y=1.8, z=0.6)),
                        ),
                        height=650,
                        template='plotly_white',
                        margin=dict(l=0, r=0, t=30, b=0),
                    )
                    st.plotly_chart(fig_surf, use_container_width=True)

                    st.caption(
                        f"Поверхность построена интерполяцией {n_points} точек "
                        f"на сетку {len(xi)}×{len(yi)}. "
                        f"Зелёные «хребты» — прибыльные зоны, красные «долины» — убыточные."
                    )

                else:
                    st.info(
                        f"Точек ({n_points}) недостаточно для регулярной поверхности. "
                        f"Показываю триангулированную mesh."
                    )

                    fig_mesh = go.Figure()
                    fig_mesh.add_trace(go.Mesh3d(
                        x=x_vals, y=y_vals, z=z_vals,
                        colorscale='RdYlGn',
                        intensity=z_vals,
                        colorbar=dict(title=z_options[z_axis], x=1.02),
                        hovertemplate=(
                            f'{all_x_options[x_axis]}: %{{x:.1f}}<br>'
                            f'{all_y_options[y_axis]}: %{{y:.1f}}<br>'
                            f'{z_options[z_axis]}: %{{z:,.1f}}<extra></extra>'
                        ),
                        name='',
                    ))

                    fig_mesh.add_trace(go.Scatter3d(
                        x=x_vals, y=y_vals, z=z_vals,
                        mode='markers+text',
                        marker=dict(size=5, color='white',
                                   line=dict(width=1, color='#333')),
                        text=labels,
                        textposition='top center',
                        textfont=dict(size=7),
                        hoverinfo='skip',
                        name='',
                    ))

                    fig_mesh.update_layout(
                        scene=dict(
                            xaxis=dict(title=all_x_options[x_axis]),
                            yaxis=dict(title=all_y_options[y_axis]),
                            zaxis=dict(title=z_options[z_axis]),
                            camera=dict(eye=dict(x=1.8, y=1.8, z=0.6)),
                        ),
                        height=650,
                        template='plotly_white',
                        margin=dict(l=0, r=0, t=30, b=0),
                        showlegend=False,
                    )
                    st.plotly_chart(fig_mesh, use_container_width=True)

            # ── Таблица с исходными данными ──
            with st.expander("📋 Исходные данные поверхности"):
                display_df = df_agg[['symbol', 'param_key', 'pnl', 'trades',
                                     'win_rate', 'volatility', 'avg_pnl']].copy()
                display_df['symbol'] = display_df['symbol'].str.replace('rfd', '')
                st.dataframe(display_df, use_container_width=True, hide_index=True)

    else:
        st.info("Нет данных для построения поверхности.")

    st.markdown("---")
    st.markdown("""
    💡 **Совет:** поверхность наиболее полезна при оптимизации параметров
    одной стратегии. Например, выбрать семейство `Stochastic` и поставить
    оси X = Параметр 1, Y = Параметр 2, Z = Суммарный PnL.
    Тогда «хребет» на поверхности покажет оптимальную зону параметров.
    """)


# ═══════════════════════════════════════════════════════════════
#  ТАБ: В РАЗРАБОТКЕ
# ═══════════════════════════════════════════════════════════════
with tab_roadmap:
    st.subheader("🚧 В разработке")

    st.markdown("Планируемые дэши. Ниже — заглушки с описанием.")

    make_empty_placeholder(
        "Drawdown Chart",
        "Просадка от пика equity. Показывает, насколько портфель «проваливался» "
        "от максимумов. Помогает оценить реальный риск и стресс-устойчивость. "
        "График: область под кривой equity, залитая красным в зоне просадки.",
        icon="📉"
    )

    make_empty_placeholder(
        "Тепловая карта PnL по часам",
        "Матрица: строки — символы или стратегии, столбцы — часы суток. "
        "Цвет ячейки — суммарный PnL за этот час. Помогает найти временные окна, "
        "где стратегии стабильно зарабатывают или сливают. "
        "Полезно для настройки торговых сессий и таймаутов.",
        icon="🕐"
    )

    make_empty_placeholder(
        "Сравнение бэктест vs реальность",
        "Сравнение ожидаемых показателей из бэктеста с фактическими результатами "
        "живой торговли. Расхождения по PnL, Win Rate, PF, просадке. "
        "Таблица с колонками: бэктест / факт / отклонение / вердикт.",
        icon="🔬"
    )

    make_empty_placeholder(
        "Sharpe по семействам",
        "Отношение средней дневной доходности к дневной волатильности. "
        "Ранжирование семейств стратегий по эффективности с учётом риска. "
        "Чем выше Sharpe — тем лучше доходность на единицу риска.",
        icon="⚖️"
    )
