import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd
import os


# ═══ КЭШ H1 ═══
symbol_data = {}

# Сколько последних H1-баров тянем из терминала при закрытии часа: больше одного
# нужно, чтобы заодно вылечить ранее записанные синтетические бары.
_SYNC_BARS = 8

# Сколько опросов ждём реальный бар, если в момент закрытия часа терминал его ещё
# не агрегировал (опрос раз в poll_interval ≈ 5 с → ~30 с ожидания).
_SYNC_RETRY_POLLS = 720   # 720 polls x 5 s = keep retrying for the whole hour instead of 30 s


def load_h1(symbol):
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M5,
                                 datetime.now() - timedelta(days=90), datetime.now())
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("time")
    # Группировка M5 → H1 с volume (sum = тиковый объём за час)
    df = df.groupby(pd.Grouper(freq="1h")).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "tick_volume": "sum"}
    ).dropna()
    df = df.rename(columns={"tick_volume": "volume"})
    # Последняя строка — незакрытый текущий час (в выборке есть формирующийся M5).
    # Для бэктеста это неполный бар, а для live он ещё и сдвигал current_hour на час
    # вперёд. Отбрасываем только если это действительно текущий час: в выходные
    # закрывающий бар пятницы оставляем.
    _now_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
    if len(df) > 1 and df.index[-1] >= _now_hour:
        df = df.iloc[:-1]
    return df


def _fetch_h1_tail(symbol, count=_SYNC_BARS):
    """Последние H1-бары из терминала: реальные O/H/L/C и tick_volume.

    Нужна, чтобы закрытый live-бар был баром терминала, а не склейкой сэмплов
    bid/ask (см. update_symbol_bar). При любой ошибке возвращает None.
    """
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, count)
    except Exception:
        return None
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("time")
    df = df.rename(columns={"tick_volume": "volume"})
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    return df[cols]


def _apply_real_bars(symbol, sd, upto_hour):
    """Подменить синтетические бары реальными (всё, что раньше `upto_hour`).

    True — если бар `upto_hour` уже лежит в df_h1 как реальный бар терминала.
    Синтетические строки в диапазоне реальных выбрасываются, поэтому повторные
    вызовы безопасны и постепенно вычищают ранее записанные огрызки.
    """
    real = _fetch_h1_tail(symbol)
    if real is None or len(real) == 0:
        return False
    real = real[real.index < upto_hour]
    if len(real) == 0:
        return False
    df = sd.get('df_h1')
    if df is None or len(df) == 0:
        sd['df_h1'] = real.copy()
    else:
        # Всё, что новее самого старого реального бара, заменяем реальными строками.
        keep = df[df.index < real.index[0]]
        merged = pd.concat([keep, real]).sort_index()
        sd['df_h1'] = merged[~merged.index.duplicated(keep='last')]
    return upto_hour in sd['df_h1'].index


def _append_synthetic_bar(sd, bar_hour):
    """Резервный путь: дописать бар из сэмплов тиков (volume неизвестен → 0).

    Используется только когда терминал ещё не отдал закрытый бар; на следующих
    опросах строка будет заменена реальным баром (_apply_real_bars).
    """
    fb = sd['forming_bar']
    new_row = pd.DataFrame(
        {'open': fb['open'], 'high': fb['high'],
         'low': fb['low'], 'close': fb['close'],
         'volume': 0},
        index=pd.DatetimeIndex([bar_hour])
    )
    sd['df_h1'] = pd.concat([sd['df_h1'], new_row])


def update_symbol_bar(symbol, bid, ask, now):
    """Обновляет формирующийся бар. Возвращает True если бар закрылся.

    Формирующийся бар по-прежнему собирается из сэмплов bid/ask (его читает
    только трейлинг), но ЗАКРЫТЫЙ час пишется в df_h1 из терминала: реальные
    open/high/low/close и tick_volume.

    Раньше закрытый бар синтезировался из сэмплов: volume=0 (все volume-зависимые
    семейства — OBV/MFI/VWAP/волновые нормализации — считали по нулям),
    open=ask / close=bid (в бар вшит спред), high/low только по опросам раз в 5 с
    (хвосты терялись). Синтетический бар никогда не заменялся реальным.
    """
    sd = symbol_data[symbol]
    bar_hour = now.replace(minute=0, second=0, microsecond=0)
    finalized = False

    if bar_hour != sd['current_hour']:
        prev_hour = sd['current_hour']
        if sd['forming_bar'] is not None:
            if _apply_real_bars(symbol, sd, prev_hour):
                sd.pop('_sync_hour', None)
                sd.pop('_sync_tries', None)
            else:
                # Терминал ещё не агрегировал час — пишем синтетику и добираем
                # реальный бар на следующих опросах (ветка else ниже).
                _append_synthetic_bar(sd, prev_hour)
                sd['_sync_hour'] = prev_hour
                sd['_sync_tries'] = 0
            finalized = True
            print(f"\n[{symbol}] Бар {prev_hour} закрыт")
        sd['current_hour'] = bar_hour
        sd['forming_bar'] = {'open': ask, 'high': ask, 'low': bid, 'close': bid}
    else:
        if sd['forming_bar'] is None:
            sd['forming_bar'] = {'open': ask, 'high': ask, 'low': bid, 'close': bid}
        else:
            sd['forming_bar']['high'] = max(sd['forming_bar']['high'], ask)
            sd['forming_bar']['low'] = min(sd['forming_bar']['low'], bid)
            sd['forming_bar']['close'] = bid

        # Добор реального бара, если при закрытии часа терминал его ещё не отдал.
        pending = sd.get('_sync_hour')
        if pending is not None:
            if _apply_real_bars(symbol, sd, pending):
                print(f"[{symbol}] Бар {pending} заменён реальным (tick_volume)", flush=True)
                sd.pop('_sync_hour', None)
                sd.pop('_sync_tries', None)
            elif sd.get('_sync_tries', 0) >= _SYNC_RETRY_POLLS:
                # Не дождались — живём на синтетическом баре этого часа.
                print(f"[{symbol}] Бар {pending} остался синтетическим "
                      f"(терминал не отдал за {_SYNC_RETRY_POLLS} опросов)", flush=True)
                sd.pop('_sync_hour', None)
                sd.pop('_sync_tries', None)
            else:
                sd['_sync_tries'] = sd.get('_sync_tries', 0) + 1

    return finalized


# ═══ ЖУРНАЛ ═══
def load_journal(JOURNAL_FILE, COLUMNS):
    if os.path.exists(JOURNAL_FILE):
        return pd.read_csv(JOURNAL_FILE, parse_dates=['entry_time', 'exit_time'])
    return pd.DataFrame(columns=COLUMNS)


def save_journal(df, JOURNAL_FILE):
    # Файл — ИСТОЧНИК ИСТИНЫ: перед записью подмешиваем то, что уже лежит на диске
    # (union по ticket). Иначе периодический save_journal(journal_df) в main.py
    # затирал сделки, записанные через record_trade: его возвращаемое значение
    # никто не сохраняет (strategy_engine._record_close), поэтому в памяти
    # оставалась старая пустая таблица и журнал всегда выглядел как «сделок не было».
    try:
        if os.path.exists(JOURNAL_FILE):
            _disk = pd.read_csv(JOURNAL_FILE, parse_dates=['entry_time', 'exit_time'])
            if len(_disk) and list(_disk.columns) == list(df.columns):
                _merged = pd.concat([_disk, df], ignore_index=True)
                if 'ticket' in _merged.columns and _merged['ticket'].notna().all():
                    _merged = _merged.drop_duplicates(subset=['ticket'], keep='last')
                df = _merged
    except (OSError, ValueError, pd.errors.ParserError) as _je:
        print(f"  [WARN] Журнал сделок: диск не прочитан ({_je!r}) — пишем как есть",
              flush=True)
    try:
        df.to_csv(JOURNAL_FILE, index=False)
    except OSError as _je:
        print(f"  [WARN] Журнал сделок не записан ({JOURNAL_FILE}): {_je!r}", flush=True)


def record_trade(trade_dict, journal_df, JOURNAL_FILE):
    # journal_df/JOURNAL_FILE могут не прийти (rerank и SL/TP в strategy_engine их не
    # передают): колонки и содержимое берём из файла — он источник истины (save_journal).
    # Возврат вызывающий код не сохраняет, поэтому сохранение делается здесь же.
    if journal_df is None:
        journal_df = pd.DataFrame()
    if not JOURNAL_FILE:
        return journal_df
    if len(journal_df.columns) == 0:
        try:
            journal_df = load_journal(JOURNAL_FILE, list(trade_dict.keys()))
        except (OSError, ValueError):
            journal_df = pd.DataFrame(columns=list(trade_dict.keys()))
    _row = pd.DataFrame([trade_dict]).reindex(columns=list(journal_df.columns))
    save_journal(pd.concat([journal_df, _row], ignore_index=True), JOURNAL_FILE)
    return journal_df
    save_journal(journal_df, JOURNAL_FILE)
    return journal_df
