"""Снимок рыночного режима на момент входа в сделку — НАБЛЮДЕНИЕ, не фильтр.

Зачем (IDEAS.md, A1 «Gate по рыночному режиму»): прежде чем что-то блокировать
по режиму рынка, нужно увидеть, как результат сделки зависит от режима. Этого
пока не видно: окно квот 14 дней и 7 символов — разбивка по режимам даёт
подвыборки по 15–30 сделок, на которых любой множитель только переобучается.
Поэтому первый шаг — измерение: считаем режим на входе и пишем его в trades.db
(таблица trade_regime), решение о гейте откладываем до накопления статистики.

Что считаем (на символ; оба признака нормированы, поэтому сравнимы между
символами и складываются в корзину):

  vi_pct   — перцентиль ATR(D1, 14) за последние `lookback` торговых дней, 0..100.
             «Громкость»: 10 — тише 90% дней, 90 — громче 90% дней.
  atr_pct  — сам ATR(D1, 14) в процентах от цены (уровень, а не ранг: перцентиль
             один и тот же у золота и у EURUSD, а масштаб движения — разный).
  k_week   — сила тренда: ER Кауфмана по H1 за последние ~168 баров, умноженный
             на sqrt(n), где n — число шагов окна. У случайного блуждания k ≈ 1;
             k ≥ 1.7 — тренд, k ≥ 2.6 — сильный тренд (те же пороги, что в
             карточках Market Regime на вкладке Overview).
  label    — 'боковик' / 'тренд' / 'сильный тренд' по k_week.

Почему ER нормируется: сырой ER структурно зависит от длины окна — у случайного
блуждания E[ER] ≈ 1/√n, то есть для недели из 168 H1-баров это ≈0.08, а для дня
из ~24 баров ≈0.20. Без умножения на √n неделя и день несопоставимы, и недельное
окно почти всегда выглядит «боковиком» даже в тренд.

Контракт: snapshot(symbol) -> dict с ключами vi_pct / atr_pct / k_week / label,
либо {} если данных нет. Функция НИКОГДА не бросает исключение и ничего не
торгует: сбой наблюдения не должен мешать исполнению.
"""

import math
import time

try:
    import MetaTrader5 as mt5
except Exception:      # терминала нет — модуль должен импортироваться всё равно
    mt5 = None


# Пороги силы тренда — те же, что в дашборде (карточки Market Regime).
_TREND_K = 1.70
_STRONG_K = 2.60

# Кэш: входов за час может быть много, а режим дня и недели меняется медленно.
# Без кэша каждый вход тянул бы из терминала ~120 D1-баров и 168 H1-баров.
_CACHE = {}            # symbol -> (ts, snapshot)
_CACHE_TTL = 3600      # секунд


def _label(k):
    """Класс силы тренда по нормированному ER."""
    if k is None:
        return ''
    if k >= _STRONG_K:
        return 'сильный тренд'
    if k >= _TREND_K:
        return 'тренд'
    return 'боковик'


def _rates(symbol, timeframe, count):
    """Последние `count` баров символа или None. Ошибки терминала не пробрасываем."""
    if mt5 is None or not symbol:
        return None
    try:
        if mt5.terminal_info() is None:
            mt5.initialize()
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    except Exception:
        return None
    if rates is None or len(rates) == 0:
        return None
    return rates


def k_week(symbol, bars=168):
    """Сила тренда по H1: ER Кауфмана × √n (≈1 — ход как у случайного блуждания)."""
    if mt5 is None:
        return None
    rates = _rates(symbol, mt5.TIMEFRAME_H1, bars)
    if rates is None or len(rates) < 60:
        return None
    closes = [float(c) for c in rates['close']]
    steps = sum(abs(closes[i] - closes[i - 1]) for i in range(1, len(closes)))
    if steps <= 0:
        return None
    er = abs(closes[-1] - closes[0]) / steps
    return float(er * math.sqrt(len(closes) - 1))


def vol_pct(symbol, period=14, lookback=100):
    """(перцентиль ATR(D1, period) за lookback дней, ATR в % от цены).

    Перцентиль — это ранг, а не уровень: он показывает, громко ли сейчас
    относительно САМОГО символа, а не относительно других пар.
    """
    if mt5 is None:
        return None, None
    rates = _rates(symbol, mt5.TIMEFRAME_D1, lookback + period + 5)
    if rates is None or len(rates) < period + 20:
        return None, None
    highs = [float(h) for h in rates['high']]
    lows = [float(lo) for lo in rates['low']]
    closes = [float(c) for c in rates['close']]
    last_close = closes[-1]
    if last_close <= 0:
        return None, None

    # True Range по классике; первый бар без предыдущего закрытия не считаем.
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    if len(trs) < period + 5:
        return None, None

    # ATR как SMA(TR, period) по всей доступной истории → ряд для перцентиля.
    atr_series = []
    for i in range(period, len(trs) + 1):
        atr_series.append(sum(trs[i - period:i]) / period)
    if not atr_series:
        return None, None
    atr_series = atr_series[-lookback:]
    atr_now = atr_series[-1]
    below = sum(1 for v in atr_series if v <= atr_now)
    pct = 100.0 * below / len(atr_series)
    atr_pct = atr_now / last_close * 100.0

    return float(pct), float(atr_pct)


def snapshot(symbol, use_cache=True):
    """Снимок режима рынка по символу: dict или {} если данных нет.

    Ключи результата: vi_pct (0..100), atr_pct (% от цены), k_week, label.
    """
    key = str(symbol)
    if use_cache:
        hit = _CACHE.get(key)
        if hit and (time.time() - hit[0]) < _CACHE_TTL:
            return dict(hit[1])
    try:
        k = k_week(key)
        pct, atr_pct = vol_pct(key)
        if k is None and pct is None:
            return {}
        out = {
            'vi_pct': pct,
            'atr_pct': atr_pct,
            'k_week': k,
            'label': _label(k),
        }
    except Exception:
        return {}
    _CACHE[key] = (time.time(), dict(out))
    return out


def reset_cache():
    """Сбросить кэш (после ручного анализа или смены дня — в тестах и скриптах)."""
    _CACHE.clear()
