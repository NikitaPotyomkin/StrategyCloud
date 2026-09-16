import streamlit as st
import pandas as pd
import os
from datetime import datetime

st.set_page_config(page_title="Strategy Cloud", layout="wide")
st.title("📊 Рэнкинг стратегий")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_DIR = os.path.join(BASE_DIR, "journals")
RANKING_FILE = os.path.join(JOURNAL_DIR, "rankings.txt")


@st.cache_data(ttl=10)
def load_rankings():
    csv_file = os.path.join(JOURNAL_DIR, "rankings.csv")
    if not os.path.exists(csv_file):
        return pd.DataFrame()
    df = pd.read_csv(csv_file)
    return df[df['top'] == 'TOP'].reset_index(drop=True)

@st.cache_data(ttl=60)
def load_journal():
    # Находишь последний journal_*.csv и читаешь
    files = [f for f in os.listdir(JOURNAL_DIR) if f.startswith("journal_") and f.endswith(".csv")]
    if not files:
        return pd.DataFrame()
    latest = max(files, key=lambda x: x)
    return pd.read_csv(os.path.join(JOURNAL_DIR, latest))

df_rank = load_rankings()
df_journal = load_journal()

st.subheader("Топ стратегий")
if not df_rank.empty:
    st.dataframe(df_rank, width="stretch")
else:
    st.warning("Файл rankings.txt не найден. Запустите main.py, чтобы начать сбор данных.")

st.subheader("Журнал сделок")
if not df_journal.empty:
    st.dataframe(df_journal.tail(50), width="stretch")
else:
    st.info("Нет сделок в журнале.")

# Кнопка для ручного обновления (опционально)
if st.button("Обновить сейчас"):
    load_rankings.clear()
    load_journal.clear()
    st.rerun()
