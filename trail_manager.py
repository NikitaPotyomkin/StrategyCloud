"""TrailManager — независимый модуль трейлинг-стопа для всех позиций StrategyCloud.

Не зависит от логики отдельных стратегий: мониторит реальные позиции
терминала по magic-пулу StrategyCloud [770000..869999] и пододвигает SL
по chandelier-логике на основе ATR(D1, period):

    long : SL = max(high с момента входа) - ATR * multiplier
    short: SL = min(low  с момента входа) + ATR * multiplier

SL двигается ТОЛЬКО в сторону прибыли, TP сохраняется. Флаг включения —
TrailParams.enabled (config.py). Интервал проверки и минимальный сдвиг
защищают от спама модификаций.
"""
import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


# ═══ МАГИЯ-ПУЛ STRATEGYCLOUD ═══
MAGIC_MIN = 770000
MAGIC_MAX = 869999

_WARNED = set()


class TrailManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self._atr_cache = {}   # symbol -> (atr, ts)
        self._last_run = None

    # ── ATR D1 ──
    def get_atr_d1(self, symbol, symbol_df_h1=None):
        """ATR(D1, period) по Уайлдеру. Приоритет: D1-бары терминала,
        фоллбэк — группировка H1 (df_h1) по календарным дням.
        """
        period = self.cfg.atr_period
        now = datetime.now()
        cached = self._atr_cache.get(symbol)
        if cached and (now - cached[1]).total_seconds() < 3600:
            return cached[0]

        atr = None
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_D1,
                                     now - timedelta(days=90), now + timedelta(days=1))
        if rates is not None and len(rates) >= period + 1:
            atr = self._atr_from_ohlc(
                rates['high'], rates['low'], rates['close'], period
            )
        elif symbol_df_h1 is not None and len(symbol_df_h1) >= period + 1:
            # Фоллбэк: H1 -> D1 (open=first, high=max, low=min, close=last)
            # Гарантируем сортировку индекса перед resample
            df_h1 = symbol_df_h1
            if not df_h1.index.is_monotonic_increasing:
                df_h1 = df_h1.sort_index()
            d1 = df_h1.resample('1D').agg(
                {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
            ).dropna()
            if len(d1) >= period + 1:
                atr = self._atr_from_ohlc(d1['high'].values, d1['low'].values,
                                          d1['close'].values, period)

        if atr is None or atr <= 0:
            self._warn(symbol, 'ATR(D1) недоступен — трейл пропущен')
            return None

        self._atr_cache[symbol] = (atr, now)
        return atr

    @staticmethod
    def _atr_from_ohlc(high, low, close, period):
        """ATR по Уайлдеру: SMA первых period TR, дальше сглаживание."""
        tr = np.empty(len(high) - 1, dtype=float)
        for i in range(1, len(high)):
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i - 1])
            lc = abs(low[i] - close[i - 1])
            tr[i - 1] = max(hl, hc, lc)
        if len(tr) < period:
            return None
        atr = float(np.mean(tr[:period]))
        for i in range(period, len(tr)):
            atr = (atr * (period - 1) + tr[i]) / period
        return atr

    # ── Основной проход ──
    def update(self, symbol_data, ticks=None):
        """Проверяет все позиции пула и пододвигает SL (chandelier ATR).

        Args:
            symbol_data: dict {symbol: {'df_h1': DataFrame, 'forming_bar': dict|None, ...}}
            ticks: dict {symbol: (bid, ask)} — свежие тики из главного цикла
        """
        if not self.cfg.enabled:
            return
        now = datetime.now()
        if self._last_run is not None and \
                (now - self._last_run).total_seconds() < self.cfg.check_interval_sec:
            return
        self._last_run = now

        positions = mt5.positions_get()
        if positions is None:
            return

        for pos in positions:
            if not (MAGIC_MIN <= pos.magic <= MAGIC_MAX):
                continue
            try:
                self._process_position(pos, symbol_data, ticks, now)
            except Exception as e:
                print(f"  [TRAIL] Ошибка {pos.symbol} ticket={pos.ticket}: {e!r}", flush=True)

    def _process_position(self, pos, symbol_data, ticks, now):
        sym = pos.symbol
        sd = symbol_data.get(sym)
        df = sd.get('df_h1') if sd else None
        atr = self.get_atr_d1(sym, df)
        if atr is None:
            return  # get_atr_d1 уже вывел предупреждение
        dist = atr * self.cfg.atr_multiplier

        # Текущая цена (тик из цикла или запрос)
        bid = ask = None
        if ticks and sym in ticks:
            bid, ask = ticks[sym]
        else:
            tick = mt5.symbol_info_tick(sym)
            if tick is not None:
                bid, ask = tick.bid, tick.ask
        if bid is None:
            return

        # ── Экстремум с момента входа ──
        # по H1-барам (индекс и pos.time — naive UTC) + формирующийся бар + тик
        entry_ts = pd.Timestamp(pos.time)
        # Синхронизация таймзон: если df.index имеет tz, локализуй entry_ts
        if df is not None and hasattr(df.index, 'tzinfo') and df.index.tzinfo is not None:
            entry_ts = entry_ts.tz_localize('UTC').tz_convert(df.index.tzinfo)
        extreme = None
        if df is not None and len(df) > 0:
            # Гарантируем сортировку для корректной фильтрации
            df_sorted = df if df.index.is_monotonic_increasing else df.sort_index()
            h1 = df_sorted[df_sorted.index >= entry_ts]
            if pos.type == mt5.POSITION_TYPE_BUY:
                extreme = float(h1['high'].max()) if len(h1) else None
            else:
                extreme = float(h1['low'].min()) if len(h1) else None
        fb = sd.get('forming_bar') if sd else None
        if fb is not None:
            if pos.type == mt5.POSITION_TYPE_BUY:
                extreme = max(extreme, fb['high']) if extreme is not None else fb['high']
            else:
                extreme = min(extreme, fb['low']) if extreme is not None else fb['low']
        if extreme is None:
            return

        # ── Новый SL ──
        if pos.type == mt5.POSITION_TYPE_BUY:
            new_sl = extreme - dist
            if pos.sl > 0 and new_sl <= pos.sl + self._min_move(sym):  # трейл только вверх
                return
            if new_sl >= bid:                                          # SL не может быть выше цены
                return
        else:
            new_sl = extreme + dist
            if pos.sl > 0 and new_sl >= pos.sl - self._min_move(sym):  # трейл только вниз
                return
            if new_sl <= ask:                                          # SL не может быть ниже цены
                return

        # ── Модификация SLTP (TP сохраняем) ──
        # Проверяем что новый SL отличается от текущего более чем на min_move
        if pos.sl > 0 and abs(new_sl - pos.sl) < self._min_move(sym):
            return  # Сдвиг слишком мал — пропускаем
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": pos.ticket,
            "symbol": sym,
            "sl": new_sl,
            "tp": pos.tp,
        }

        result = mt5.order_send(request)
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            side = 'LONG ' if pos.type == mt5.POSITION_TYPE_BUY else 'SHORT'
            print(f"  [TRAIL] {sym} {side} ticket={pos.ticket}: "
                  f"SL {pos.sl:.5f} -> {new_sl:.5f} (ATR={atr:.5f})", flush=True)
        elif result is not None and result.retcode != mt5.TRADE_RETCODE_PLACED:
            self._warn(sym, f"модификация SL ticket={pos.ticket} отклонена: "
                            f"retcode={result.retcode} ({result.comment})")

    def _min_move(self, symbol):
        """Минимальный сдвиг SL в пунктах (чтобы не спамить модификациями)."""
        point = 0.00001
        info = mt5.symbol_info(symbol)
        if info is not None and info.point:
            point = info.point
        return self.cfg.min_move_points * point

    def _warn(self, symbol, msg):
        if (symbol, msg) not in _WARNED:
            _WARNED.add((symbol, msg))
            print(f"  [TRAIL] {symbol}: {msg}", flush=True)