"""Журнал сделок и оконная арифметика для инкрементального пересчёта.

Зачем
-----
Метрики комбинации нельзя пересчитать на сдвинутом (скользящем) окне, имея только
агрегаты (n_trades, win_rate, profit_factor, score): арифметика нелинейна. Нужен
список сделок. Он лежит в чекпойнте v2 (functions.save_checkpoint, поле 'trades'
у каждой комбинации) и обновляется дёшево — снять крайние сделки, добавить новые.

Формат записи сделки: [entry_epoch, exit_epoch, dir(+1 long / -1 short), profit]
Окно отсекается по ВРЕМЕНИ ВЫХОДА: сделка, закрытая внутри окна, остаётся (её
результат известен), закрытая раньше — выбывает.

Границы применимости
--------------------
Журнал даёт точное обновление метрик только вместе с корректным warm-up индикаторов
(см. strategies/_warmup.py): exact-индикаторы досчитываются точно, exp-индикаторы — с
заданным запасом, а cum (A/D, OBV, cumsum) и model (RF/LogReg/coint) инкрементально
считать нельзя, они пересчитываются полностью. Расхождение инкремента с полным
расчётом ловит parity-гейт (см. parity ниже).

Модуль — только арифметика над журналом: без бэктеста, без MT5, без файлов.
"""

from strategies._bt_core import TradeList, trade_row

__all__ = ['TradeList', 'trade_row', 'TRADE_LOG_VERSION', 'WINDOW_DAYS_DEFAULT',
           'window_start_epoch', 'trim', 'merge', 'profits', 'is_capable',
           'parity', 'summary', 'merge_incremental']

# Версия формата журнала (совпадает с версией чекпойнта в functions.py).
TRADE_LOG_VERSION = 2

# Окно бэктеста по умолчанию — как backtest_days в config.py.
WINDOW_DAYS_DEFAULT = 30


def window_start_epoch(end_epoch, window_days=WINDOW_DAYS_DEFAULT):
    """Начало окна (epoch, включительно) для журнала, заканчивающегося в end_epoch."""
    return int(end_epoch) - int(window_days) * 86400


def trim(trades, window_start):
    """Оставить сделки, закрытые не раньше window_start; отсортировать по выходу."""
    if not trades:
        return []
    kept = [t for t in trades if t and len(t) >= 4 and int(t[1]) >= int(window_start)]
    kept.sort(key=lambda t: int(t[1]))
    return kept


def merge(old_trades, new_trades, window_start):
    """Новое окно = старый журнал + досчитанные сделки, обрезанное по окну.

    Дубли отсекаются по (вход, выход, профит): при инкрементальном прогоне последний
    посчитанный бар пересчитывается вместе с warm-up, поэтому одну и ту же сделку
    можно получить дважды — оставляем одну.
    """
    seen = set()
    out = []
    for t in list(old_trades or []) + list(new_trades or []):
        if not t or len(t) < 4:
            continue
        key = (int(t[0]), int(t[1]), round(float(t[3]), 2))
        if key in seen:
            continue
        seen.add(key)
        out.append([int(t[0]), int(t[1]), int(t[2]), round(float(t[3]), 2)])
    return trim(out, window_start)


def merge_incremental(old_trades, new_trades, cached_bar_epoch, window_start):
    """Журнал после ХВОСТОВОГО пересчёта новых баров (инкремент).

    old_trades       — журнал из чекпойнта v2 (полный прогон, история кончалась на
                       баре cached_bar_epoch);
    new_trades       — сделки, посчитанные на срезе [warm-up .. now];
    cached_bar_epoch — бар, до которого история уже обсчитана;
    window_start     — начало окна (epoch) по времени ВЫХОДА сделки.

    Правило границы: старый прогон обрывался на cached_bar_epoch, поэтому в нём есть
    только закрытые сделки. Значит сделки среза, закрытые НЕ ПОЗЖЕ cached_bar_epoch,
    — это уже посчитанное (выбрасываем), а закрытые позже — новые. Дубликаты на
    стыке отсекаются по (вход, выход, профит). Окно применяется по времени выхода.
    """
    cbe = int(cached_bar_epoch)
    keep_old = [t for t in (old_trades or []) if t and len(t) >= 4 and int(t[1]) <= cbe]
    keep_new = [t for t in (new_trades or []) if t and len(t) >= 4 and int(t[1]) > cbe]
    seen = set()
    out = []
    for t in keep_old + keep_new:
        key = (int(t[0]), int(t[1]), round(float(t[3]), 2))
        if key in seen:
            continue
        seen.add(key)
        out.append([int(t[0]), int(t[1]), int(t[2]), round(float(t[3]), 2)])
    return trim(out, window_start)


def profits(trades):
    """Профиты сделок по порядку — на вход calc_metrics/composite_score."""
    return [float(t[3]) for t in (trades or []) if t and len(t) >= 4]


def is_capable(trades, min_rows=1):
    """Годится ли журнал для инкремента: сделки есть и все записи корректны."""
    if not trades or len(trades) < min_rows:
        return False
    return all(t and len(t) >= 4 for t in trades)


def parity(old_trades, new_trades, tol=1e-6):
    """Сравнить журналы (инкремент vs полный расчёт) для parity-гейта.

    Возвращает (ok, diff): diff — максимальное расхождение профитов по порядку сделок,
    inf — если разошлось число сделок (сигналы поехали, инкремент для семьи запрещаем).
    """
    a, b = profits(old_trades), profits(new_trades)
    if len(a) != len(b):
        return False, float('inf')
    diff = 0.0
    for x, y in zip(a, b):
        diff = max(diff, abs(x - y))
    return diff <= tol, diff


def summary(trades):
    """Краткая сводка журнала — для логов и глазной проверки."""
    p = profits(trades)
    wins = [x for x in p if x > 0]
    losses = [x for x in p if x < 0]
    return {
        'n': len(p),
        'profit': round(sum(p), 2),
        'win_rate': round(len(wins) / len(p), 4) if p else 0.0,
        'gross_win': round(sum(wins), 2),
        'gross_loss': round(sum(losses), 2),
    }
