import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime, timedelta

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

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
def load_journal(magic_filter=None, days_back=30):
    """Получает историю сделок из MetaTrader 5.

    Args:
        magic_filter: int или список int — magic-номера стратегий.
                      Если None — берутся все сделки.
        days_back:    сколько дней истории загружать.

    Returns:
        DataFrame с колонками: timestamp, ticket, symbol, type, entry,
        volume, price, profit, commission, swap, profit_net, magic, comment
    """
    if not MT5_AVAILABLE:
        st.error("MetaTrader5 не установлен. Установите: pip install MetaTrader5")
        return pd.DataFrame()

    mt5.shutdown()
    if not mt5.initialize():
        st.error(f"MT5 init failed: {mt5.last_error()}")
        return pd.DataFrame()

    date_to = datetime.now()
    date_from = date_to - timedelta(days=days_back)

    deals = mt5.history_deals_get(date_from, date_to)

    if deals is None or len(deals) == 0:
        mt5.shutdown()
        return pd.DataFrame()

    df = pd.DataFrame(list(deals), columns=[
        'ticket', 'order', 'time', 'time_msc', 'type', 'entry',
        'magic', 'position_id', 'volume', 'price', 'commission',
        'swap', 'profit', 'symbol', 'comment', 'external_id'
    ])

    mt5.shutdown()

    # Фильтр по magic
    if magic_filter is not None:
        if isinstance(magic_filter, int):
            magic_filter = [magic_filter]
        df = df[df['magic'].isin(magic_filter)]

    # Исключаем балансные операции
    df = df[df['entry'] != mt5.DEAL_ENTRY_OUT_BY]

    # Метки времени
    df['timestamp'] = pd.to_datetime(df['time'], unit='s')
    df['profit_net'] = df['profit'] + df['commission'] + df['swap']

    # Расшифровка type и entry
    type_map = {
        mt5.DEAL_TYPE_BUY: 'buy',
        mt5.DEAL_TYPE_SELL: 'sell',
        mt5.DEAL_TYPE_BALANCE: 'balance',
        mt5.DEAL_TYPE_CREDIT: 'credit',
    }
    entry_map = {
        mt5.DEAL_ENTRY_IN: 'open',
        mt5.DEAL_ENTRY_OUT: 'close',
        mt5.DEAL_ENTRY_INOUT: 'reverse',
    }
    df['type'] = df['type'].map(type_map).fillna('other')
    df['entry'] = df['entry'].map(entry_map).fillna('other')

    # Только торговые сделки
    df = df[df['type'].isin(['buy', 'sell'])]

    df = df.sort_values('timestamp').reset_index(drop=True)
    return df


# ── Настройки фильтра ──
with st.sidebar:
    st.subheader("Настройки")
    days_back = st.slider("История сделок (дней)", 1, 90, 30)
    use_magic_filter = st.checkbox("Фильтр по magic", value=False)
    magic_input = st.text_input("Magic (через запятую)", "1000-1099")

    if use_magic_filter:
        try:
            parts = magic_input.split(',')
            magics = []
            for p in parts:
                p = p.strip()
                if '-' in p:
                    a, b = p.split('-')
                    magics.extend(range(int(a), int(b) + 1))
                else:
                    magics.append(int(p))
            magic_filter = magics
        except ValueError:
            st.warning("Неверный формат magic")
            magic_filter = None
    else:
        magic_filter = None


# ── Загрузка данных ──
state = load_active_state()
df_journal = load_journal(magic_filter=magic_filter, days_back=days_back)


# ── Расчет прогноза PnL ──
forecast_pnl = None
if not df_journal.empty:
    closed = df_journal[df_journal['entry'] == 'close'].copy()
    if not closed.empty:
        daily_avg = closed.groupby(closed['timestamp'].dt.date)['profit_net'].sum().mean()
        if pd.notna(daily_avg):
            forecast_pnl = daily_avg * 21


# ── Сводка (Баланс, Квота, Прогноз) ──
if state:
    col1, col2, col3 = st.columns(3)
    updated = datetime.fromisoformat(state['updated']).strftime('%H:%M:%S')

    with col1:
        st.metric("Баланс", f"{state['balance']:,.0f} руб")
    with col2:
        st.metric("Квота риска", f"{state['quota']:,.0f} руб")
    with col3:
        if forecast_pnl is not None:
            st.metric("Прогноз PnL (мес)", f"{forecast_pnl:,.1f} руб",
                      delta_color="normal")
        else:
            st.metric("Прогноз PnL (мес)", "Нет данных")

    st.caption(f"Обновлено: {updated}")

    # ── Торгующие стратегии ──
    st.subheader("Торгующие стратегии")
    df_active = pd.DataFrame(state['strategies'])

    if not df_active.empty:
        df_active = df_active.sort_values('score', ascending=False).reset_index(drop=True)
        df_active['статус'] = df_active['has_position'].apply(
            lambda x: '🟢 в позиции' if x else '⚪ ожидание'
        )

        display_cols = ['статус', 'symbol', 'type', 'k_period',
                        'sl_points', 'tp_points', 'score', 'lot',
                        'profit', 'profit_factor', 'win_rate', 'n_trades']
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

        # ── Распределение по символам ──
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
st.subheader("Журнал сделок (MT5)")
if not df_journal.empty:
    show_cols = ['timestamp', 'symbol', 'type', 'entry', 'volume',
                 'price', 'profit', 'commission', 'swap', 'profit_net',
                 'magic', 'comment']
    cols_available = [c for c in show_cols if c in df_journal.columns]

    st.dataframe(
        df_journal[cols_available].tail(50),
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
    st.caption(f"Всего сделок за {days_back} дн.: {len(df_journal)}")
else:
    if not MT5_AVAILABLE:
        st.info("Установите MetaTrader5: pip install MetaTrader5")
    else:
        st.info("Нет сделок в истории MT5 за выбранный период.")


# ── Кнопка обновления ──
if st.button("🔄 Обновить"):
    load_active_state.clear()
    load_journal.clear()
    st.rerun()
