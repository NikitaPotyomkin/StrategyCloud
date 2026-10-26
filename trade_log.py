"""Журнал сделок комбинации и оконная арифметика.

Зачем
-----
Чекпойнт v2 (functions.save_checkpoint) хранит у каждой комбинации список сделок —
он нужен, чтобы видеть состав результатов, а не только агрегаты.

Формат записи сделки: [entry_epoch, exit_epoch, dir(+1 long / -1 short), profit]
Окно отсекается по ВРЕМЕНИ ВЫХОДА: сделка, закрытая внутри окна, остаётся
(её результат известен), закрытая раньше — выбывает.

Модуль — только арифметика над журналом: без бэктеста, без MT5, без файлов.
"""

from strategies._bt_core import TradeList, trade_row

__all__ = ['TradeList', 'trade_row', 'TRADE_LOG_VERSION', 'WINDOW_DAYS_DEFAULT',
           'window_start_epoch', 'trim', 'merge', 'profits', 'summary']

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
    """Новое окно = старый журнал + новые сделки, обрезанное по окну.

    Дубли отсекаются по (вход, выход, профит): один и тот же бар может дать одну и
    ту же сделку дважды — оставляем одну.
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


def profits(trades):
    """Профиты сделок по порядку — на вход calc_metrics/composite_score."""
    return [float(t[3]) for t in (trades or []) if t and len(t) >= 4]


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
