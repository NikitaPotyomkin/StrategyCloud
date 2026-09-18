import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime

st.set_page_config(page_title="Strategy Cloud", layout="wide")
st.title("📊 Рэнкинг стратегий")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_DIR = os.path.join(BASE_DIR, "journals")
ACTIVE_FILE = os.path.join(JOURNAL_DIR, "active_state.json")


@st.cache_data(ttl=10)
def load_active_state():
    if not os.path.exists(ACTIVE_FILE):
        return None
    with open(ACTIVE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


@st.cache_data(ttl=60)
def load_journal():
    files = [f for f in os.listdir(JOURNAL_DIR)
             if f.startswith("journal_") and f.endswith(".csv")]
    if not files:
        return pd.DataFrame()
    latest = max(files, key=lambda x: x)
    return pd.read_csv(os.path.join(JOURNAL_DIR, latest))


# ── Активные стратегии ──
state = load_active_state()

if state:
    # Сводка сверху
    col1, col2, col3, col4 = st.columns(4)
    updated = datetime.fromisoformat(state['updated']).strftime('%H:%M:%S')
    with col1:
        st.metric("Баланс", f"{state['balance']:,.0f} руб")
    with col2:
        st.metric("Квота риска", f"{state['quota']:,.0f} руб")
    with col3:
        st.metric("Активных стратегий", state['total_strategies'])
    with col4:
        pos_count = sum(1 for s in state['strategies'] if s['has_position'])
        st.metric("Открытых позиций", pos_count)

    st.caption(f"Обновлено: {updated}")

    st.subheader("Торгующие стратегии")

    df_active = pd.DataFrame(state['strategies'])

    if not df_active.empty:
        # Сортируем по скорингу
        df_active = df_active.sort_values('score', ascending=False).reset_index(drop=True)

        # Цветовая метка: зелёный — позиция открыта
        df_active['статус'] = df_active['has_position'].apply(
            lambda x: '🟢 в позиции' if x else '⚪ ожидание'
        )

        # Выбираем колонки для показа
        display_cols = ['статус', 'symbol', 'type', 'k_period',
                        'sl_points', 'tp_points', 'score', 'lot',
                        'profit', 'profit_factor', 'win_rate', 'n_trades']
        # Убираем колонки с '-', если все значения '-'
        cols_to_show = [c for c in display_cols if c in df_active.columns]

        st.dataframe(
            df_active[cols_to_show],
            use_container_width=True,
            column_config={
                'score': st.column_config.NumberColumn(format="%.3f"),
                'lot': st.column_config.NumberColumn(format="%.2f"),
                'profit': st.column_config.NumberColumn(format="%.1f"),
                'profit_factor': st.column_config.NumberColumn(format="%.2f"),
                'win_rate': st.column_config.NumberColumn(format="%.0f%%"),
            },
            hide_index=True,
        )

        # Распределение по символам
        st.subheader("Распределение по символам")
        by_symbol = df_active.groupby('symbol').agg(
            стратегий=('symbol', 'count'),
            лот=('lot', 'sum'),
            в_позиции=('has_position', 'sum'),
        ).reset_index()
        st.dataframe(by_symbol, use_container_width=True, hide_index=True)

    else:
        st.warning("Нет активных стратегий.")
else:
    st.warning("Файл active_state.json не найден. Запустите main.py.")


# ── Журнал сделок ──
st.subheader("Журнал сделок")
df_journal = load_journal()
if not df_journal.empty:
    st.dataframe(df_journal.tail(50), use_container_width=True, hide_index=True)
else:
    st.info("Нет сделок в журнале.")


# ── Кнопка обновления ──
if st.button("Обновить"):
    load_active_state.clear()
    load_journal.clear()
    st.rerun()
