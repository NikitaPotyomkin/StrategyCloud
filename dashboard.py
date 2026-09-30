import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

from daily_report import get_dashboard_data

st.set_page_config(page_title="Strategy Cloud", layout="wide")
st.title("📊 Рэнкинг стратегий")


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


# ── Настройки ──
with st.sidebar:
    st.subheader("Настройки")
    days_back = st.slider("История сделок (дней)", 1, 90, 30)
    st.caption("Данные обновляются каждые 30 секунд")


# ── Загрузка данных из единой точки входа ──
data = load_dashboard_data(days_back)


# ── Отображение данных ──
if data:
    # ── Сводка (Баланс, Квота, Прогноз) ──
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
            x=df_strat['pnl'],
            y=df_strat['name'],
            orientation='h',
            marker_color=colors_strat,
            text=df_strat['trades'],
            textposition='outside',
            texttemplate='%{text}',
            hovertemplate=(
                '<b>%{y}</b><br>PnL: %{x:,.1f} руб<br>Сделок: %{text}'
                '<extra></extra>'
            ),
            name='',
        ))
        fig1.update_layout(
            height=max(450, len(df_strat) * 24),
            xaxis_title='PnL (руб)',
            yaxis_title='',
            showlegend=False,
            template='plotly_white',
            margin=dict(l=20, r=80, t=20, b=40),
            bargap=0.15,
        )
        st.plotly_chart(fig1, use_container_width=True)
        st.caption("Числа на столбцах — количество сделок за период")

    # ── PnL по семействам стратегий ──
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
            x=df_fam['strategy_type'],
            y=df_fam['pnl'],
            marker_color=colors_fam,
            text=df_fam['trades'],
            textposition='outside',
            texttemplate='%{text}',
            hovertemplate=(
                '<b>%{x}</b><br>PnL: %{y:,.1f} руб<br>Сделок: %{text}'
                '<extra></extra>'
            ),
            name='',
        ))
        fig2.add_hline(y=0, line_dash='dash', line_color='gray', opacity=0.5)
        fig2.update_layout(
            height=400,
            xaxis_title='Семейство стратегий',
            yaxis_title='PnL (руб)',
            showlegend=False,
            template='plotly_white',
            margin=dict(l=60, r=20, t=20, b=60),
            bargap=0.25,
            xaxis={'categoryorder': 'total ascending'},
        )
        st.plotly_chart(fig2, use_container_width=True)
        st.caption("Числа на столбцах — количество сделок за период")

    # ── Exposure heatmap: активность по символам во времени ──
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
            index='symbol',
            columns='bucket',
            values='profit_net',
            aggfunc='count',
            fill_value=0,
        )

        symbols_order = sorted(pivot.index)
        pivot = pivot.loc[symbols_order]
        display_symbols = [s.replace('rfd', '') for s in pivot.index]
        time_labels = [col.strftime(bucket_fmt) for col in pivot.columns]

        z_max = max(3, pivot.values.max())

        fig_heat = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=time_labels,
            y=display_symbols,
            colorscale=[
                [0.0, '#f5f5f5'],
                [0.33, '#81C784'],
                [0.66, '#FFB74D'],
                [1.0, '#E53935'],
            ],
            zmin=0,
            zmax=z_max,
            text=pivot.values,
            texttemplate='%{text}',
            textfont=dict(size=10),
            hovertemplate=(
                'Символ: %{y}<br>Время: %{x}<br>Сделок: %{z}'
                '<extra></extra>'
            ),
        ))

        fig_heat.update_layout(
            height=350,
            xaxis_title='Время',
            yaxis_title='Символ',
            template='plotly_white',
            margin=dict(l=80, r=20, t=20, b=60),
            xaxis=dict(tickangle=-45),
        )
        st.plotly_chart(fig_heat, use_container_width=True)
        st.caption("Цвет: 0 сделок — серый, 1–2 — зелёный, 3 (лимит) — оранжевый, >3 — красный (баг)")

    # ── Risk gauge: использование квоты ──
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
                    'count': 0,
                    'volume': 0.0,
                    'pnl': 0.0,
                    'max_loss': 0.0,
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
            height=220,
            template='plotly_white',
            margin=dict(l=40, r=40, t=10, b=10),
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

        if risk_by_symbol:
            df_risk = pd.DataFrame([
                {'symbol': s, **v} for s, v in risk_by_symbol.items()
            ]).sort_values('max_loss', ascending=True)

            df_risk['display_sym'] = df_risk['symbol']
            risk_colors = make_gradient_colors(
                [-x for x in df_risk['max_loss']]
            )

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
                yaxis_title='',
                showlegend=False,
                template='plotly_white',
                margin=dict(l=80, r=60, t=10, b=40),
                bargap=0.2,
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

    # ── Облако сделок (Scatter) ──
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

        fig.add_hline(
            y=0,
            line_dash="dash",
            line_color="gray",
            opacity=0.5
        )

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

    # ── Торгующие стратегии ──
    st.subheader("Торгующие стратегии")
    if data['active_strategies']:
        df_active = pd.DataFrame(data['active_strategies'])
        df_active = df_active.sort_values('lot', ascending=False).reset_index(drop=True)
        df_active['статус'] = df_active['has_position'].apply(
            lambda x: '🟢 в позиции' if x else '⚪ ожидание'
        )

        display_cols = ['статус', 'symbol', 'type', 'param_key',
                        'lot', 'magic']
        cols_to_show = [c for c in display_cols if c in df_active.columns]

        st.dataframe(
            df_active[cols_to_show],
            use_container_width=True,
            column_config={
                'lot': st.column_config.NumberColumn(format="%.2f"),
                'magic': st.column_config.NumberColumn(format="%.0f"),
            },
            hide_index=True,
        )

        # ── Распределение по символам ──
        st.subheader("Распределение по символам")
        by_symbol = df_active.groupby('symbol').agg(
            стратегий=('symbol', 'count'),
            лот=('lot', 'sum'),
            в_позиции=('has_position', 'sum'),
        ).reset_index()
        st.dataframe(by_symbol, use_container_width=True, hide_index=True)
    else:
        st.info("Нет открытых позиций.")

    # ── Журнал сделок ──
    st.subheader("Журнал сделок (последние 50)")
    if not data['trades_df'].empty:
        show_cols = ['timestamp', 'symbol', 'strategy_type', 'param_key',
                     'type', 'entry', 'volume',
                     'price', 'profit', 'commission', 'swap', 'profit_net',
                     'magic']
        cols_available = [c for c in show_cols if c in data['trades_df'].columns]

        st.dataframe(
            data['trades_df'][cols_available].tail(50),
            use_container_width=True,
            hide_index=True,
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

else:
    st.warning("Не удалось загрузить данные. Убедитесь, что MT5 запущен.")


# ── Кнопка обновления ──
if st.button("🔄 Обновить"):
    load_dashboard_data.clear()
    st.rerun()
