import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd
import os


# ═══ КЭШ H1 ═══
symbol_data = {}


def load_h1(symbol):
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5,
                                 datetime.now() - timedelta(days=90), datetime.now())
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("time")[["open", "high", "low", "close"]]
    df = df.groupby(pd.Grouper(freq="1h")).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return df


def update_symbol_bar(symbol, bid, ask, now):
    """Обновляет формирующийся бар. Возвращает True если бар закрылся."""
    sd = symbol_data[symbol]
    bar_hour = now.replace(minute=0, second=0, microsecond=0)
    finalized = False
    if bar_hour != sd['current_hour']:
        if sd['forming_bar'] is not None:
            new_row = pd.DataFrame(
                {'open': sd['forming_bar']['open'], 'high': sd['forming_bar']['high'],
                 'low': sd['forming_bar']['low'], 'close': sd['forming_bar']['close']},
                index=pd.DatetimeIndex([sd['current_hour']])
            )
            sd['df_h1'] = pd.concat([sd['df_h1'], new_row])
            finalized = True
            print(f"\n[{symbol}] Бар {sd['current_hour']} закрыт")
        sd['current_hour'] = bar_hour
        sd['forming_bar'] = {'open': ask, 'high': ask, 'low': bid, 'close': bid}
    else:
        if sd['forming_bar'] is None:
            sd['forming_bar'] = {'open': ask, 'high': ask, 'low': bid, 'close': bid}
        else:
            sd['forming_bar']['high'] = max(sd['forming_bar']['high'], ask)
            sd['forming_bar']['low'] = min(sd['forming_bar']['low'], bid)
            sd['forming_bar']['close'] = bid
    return finalized


# ═══ ЖУРНАЛ ═══
def load_journal(JOURNAL_FILE, COLUMNS):
    if os.path.exists(JOURNAL_FILE):
        return pd.read_csv(JOURNAL_FILE, parse_dates=['entry_time', 'exit_time'])
    return pd.DataFrame(columns=COLUMNS)


def save_journal(df, JOURNAL_FILE):
    df.to_csv(JOURNAL_FILE, index=False)


def record_trade(trade_dict, journal_df, JOURNAL_FILE):
    journal_df = pd.concat([journal_df, pd.DataFrame([trade_dict])], ignore_index=True)
    save_journal(journal_df, JOURNAL_FILE)
    return journal_df
