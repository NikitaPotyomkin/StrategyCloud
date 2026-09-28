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

# Импорт единой точки входа
from daily_report import get_dashboard_data

st.set_page_config(page_title="Strategy Cloud", layout="wide")
st.title("📊 Рэнкинг стратегий")


@st.cache_data(ttl=30)
def load_dashboard_data(days_back=30):
    """Единая точка входа — все данные для дэшборда из daily_report.py"""
    return get_dashboard_data(days_back)


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
        # Прогноз PnL
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

    # ── Облако сделок (Scatter) ──
    if not data['trades_df'].empty and PLOTLY_AVAILABLE:
        st.subheader("☁️ Облако сделок")

        df_sorted = data['trades_df'].sort_values('timestamp').copy()

        # Цвета: зелёный для прибыли, красный для убытка
        colors = ['#26A69A' if x >= 0 else '#EF5350' for x in df_sorted['profit_net']]

        fig = go.Figure()

        # Scatter plot — каждая точка = сделка
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

        # Горизонтальная линия 0
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
        show_cols = ['timestamp', 'symbol', 'type', 'entry', 'volume',
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
