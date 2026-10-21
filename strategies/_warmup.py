"""Декларативный warm-up стратегий для инкрементального пересчёта.

НАЗНАЧЕНИЕ
    Ответ на один вопрос: сколько баров истории нужно подать калькулятору ДО
    первого пересчитываемого бара, чтобы «хвостовой» пересчёт дал ТЕ ЖЕ значения,
    что полный прогон по всему окну.

    Пока модуль не вызывается боевым кодом: инкремент включается вместе с переходом
    на длинное окно (180 дней) и research-демоном. Смысл — завести классификацию
    заранее и в одном месте, чтобы к моменту включения она была проверена.

КЛАССЫ ПАМЯТИ (тип индикатора определяет warm-up, а не «на глазок»):
    exact — фиксированные rolling-окна (SMA/BB/std, percentile, runs, donchian,
            ichimoku senkou+displacement, ширина z-score): значения ТОЧНЫЕ,
            достаточно «окно минус один бар» плюс задержки стратегии.
    exp   — экспоненциальное сглаживание (EMA/Wilder ATR/RSI/MACD/EWM): память
            формально бесконечна, но на 5 периодах вес старого шока ~e^-5 < 1%,
            поэтому warm-up = 5 x период.
    cum   — кумулятивные ряды (A/D, OBV, cumsum): уровень зависит от ВСЕЙ истории,
            срез даёт другой масштаб → инкремент запрещён (warmup = None).
    model — обучаемые модели (RF, LogReg, coint): модель обучена на окне,
            «дописать бар» нечем → инкремент запрещён (warmup = None).

ПРАВИЛО ГРАНИЦЫ ОКНА (обязательно для вызывающего кода)
    Инкремент обязан выбрасывать сделки с временем входа раньше (конец окна - окно),
    иначе rolling-метрики (mdd/sharpe/recovery) постепенно превратятся из 30-дневных
    в 90-дневные. Для этого в чекпойнте нужен список сделок, а не только агрегаты
    (schema v2) — сейчас агрегатов недостаточно.
"""
import os
from datetime import datetime, timedelta
import json

# ── Классы памяти ──
MEMORY_EXACT = 'exact'
MEMORY_EXP = 'exp'
MEMORY_CUM = 'cum'
MEMORY_MODEL = 'model'

# Множитель для экспоненциальной памяти: 5 периодов ≈ 0.7% остаточного веса.
EXP_MULTIPLIER = 5

# Типовой период семейства, когда точный параметр сетки неизвестен (оценка warm-up).
# Консервативно: лучше взять больше истории, чем исказить метрики недогревом.
HINT_PERIOD_EXACT = 120
HINT_PERIOD_EXP = 60

# ── Реестр стратегий (strategies/_registry.py, ENABLED_BATCH) ──
EXACT_KEYS = (
    'vwmacd', 'cmf', 'dpo', 'vortex', 'bbwalk', 'bbrsi', 'bbmacd', 'adxbb', 'roc',
    'pearson', 'partcorr', 'dyncorr', 'corrbreak', 'covbreak', 'voltrend', 'volspike',
    'ichimoku_tk', 'ichimoku_cloud', 'ichimoku_chikou', 'ichimoku_full',
    'fibonacci', 'monthlyhl', 'prevweek', 'monpivot', 'weekpivot', 'pivotbounce',
    'asianbreak', 'firstbar', 'gapfill', 'dowmom', 'rangedaily', 'doji', 'dbltopbot',
    'srbounce', 'threecrows', 'tweezer', 'insidebar', 'mfi', 'spearman', 'donchadx',
    'donchian_vol', 'coinflip',
)

EXP_KEYS = (
    'triple_ema', 'adx_di', 'hull', 'dualema', 'macdline', 'wmaema', 'ppo', 'elder',
    'tsi', 'ema2050', 'ribbon', 'macdema', 'adxbreak', 'forceidx', 'stochma',
    'stochrsiema', 'cciext', 'obvema', 'macdrsi', 'emapara', 'atrrev', 'keltatr',
    'keltbreak', 'atrchan', 'rsiob', 'stochastic_rsi', 'macdzero', 'rsieema',
    'smoothedma', 'willstoch', 'strema', 'tworsi',
)

CUM_KEYS = (
    'adline', 'obvslope',
)

MODEL_KEYS = (
    'rf', 'logreg', 'coint',
)

# ── Легаси-семейства (functions.py: _backtest_*, strat_combo_map) ──
# Добавлены заранее: используются после унификации спек (см. дорожную карту).
LEGACY_EXACT_KEYS = (
    'percentile', 'runs', 'donchian', 'bb_squeeze', 'vwap', 'momentum', 'engulfing',
    'pin_bar', 'prev_daily', 'morning_star', 'ichimoku', 'bollinger', 'macd_histogram',
)
LEGACY_EXP_KEYS = (
    'ma', 'ema_cross', 'macd_cross', 'rsi_rev', 'rsi_div', 'atr', 'autocorr', 'hurst',
    'lrc', 'sharpe', 'skewness', 'bayesian', 'kurtosis', 'chi_square', 'corr_momentum',
    'williams_r', 'cci', 'supertrend', 'adx', 'zscore', 'stoch', 'parabolic',
)
LEGACY_CUM_KEYS = (
    'obv',
)


def memory_class(key):
    """Класс памяти стратегии по её ключу.

    Неизвестный ключ → MEMORY_CUM (консервативно): инкремент запрещён, считаем
    полным прогоном. Ошибиться в сторону «посчитать лишнее» безопаснее, чем
    молча исказить метрики отбора.
    """
    if key in MODEL_KEYS or key in ('rf', 'logreg', 'coint'):
        return MEMORY_MODEL
    if key in CUM_KEYS or key in LEGACY_CUM_KEYS:
        return MEMORY_CUM
    if key in EXACT_KEYS or key in LEGACY_EXACT_KEYS:
        return MEMORY_EXACT
    if key in EXP_KEYS or key in LEGACY_EXP_KEYS:
        return MEMORY_EXP
    return MEMORY_CUM


def warmup_bars(key, param=None, min_len=0, window_bars=720, multiplier=EXP_MULTIPLIER):
    """Сколько баров истории подать калькулятору до первого пересчитываемого бара.

    Возвращает int (в барах) либо None — «хвостовой» пересчёт для этой стратегии
    недопустим, нужен полный прогон по окну.

    key         — ключ стратегии (см. ENABLED_BATCH / strat_combo_map)
    param       — основной период стратегии (если известен)
    min_len     — минимальная длина истории из реестра (entry['min_len'])
    window_bars — длина окна бэктеста (BACKTEST_DAYS * 24)
    """
    cls = memory_class(key)
    if cls in (MEMORY_CUM, MEMORY_MODEL):
        return None
    try:
        period = int(param) if param is not None else 0
    except (TypeError, ValueError):
        period = 0
    if period <= 0:
        # Параметр сетки неизвестен — берём типовой период класса памяти (консервативно).
        period = HINT_PERIOD_EXACT if cls == MEMORY_EXACT else HINT_PERIOD_EXP
    base = max(int(min_len or 0), period)
    if cls == MEMORY_EXACT:
        # Rolling-окно: точное значение требует «окно - 1» бар, плюс 2 бара запаса
        # на сами границы расчёта.
        return max(base - 1 + 2, 3)
    # exp: 5 периодов, но не меньше min_len из реестра.
    return max(base * multiplier, int(min_len or 0), 10)


def incremental_ok(key, param=None, min_len=0, window_bars=720):
    """True, если стратегию можно пересчитывать «хвостом» на новых барах."""
    return warmup_bars(key, param, min_len, window_bars) is not None


# ═══ ЖУРНАЛ ПРОВЕРОК ПАРИТЕТА ═══
# Инкремент нельзя считать доказанным: после включения хвостового пересчёта метрики
# каждой стратегии сравниваются с полным прогоном на выборке. Расхождение выше
# допуска → стратегия попадает сюда и больше не считается инкрементально
# (автоматическая понижение до полного прогона).
PARITY_TOL = 1e-6


def parity_file(checkpoint_dir):
    """Путь к журналу паритета (лежит рядом с чекпойнтами)."""
    return os.path.join(checkpoint_dir, 'incremental_parity.json')


def load_parity(checkpoint_dir):
    """{key: {'ok': bool, 'max_diff': float, 'checked_at': iso}}."""
    path = parity_file(checkpoint_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def save_parity(checkpoint_dir, data):
    path = parity_file(checkpoint_dir)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def record_parity(checkpoint_dir, key, max_diff, tol=PARITY_TOL):
    """Записать результат проверки паритета инкремента против полного прогона."""
    data = load_parity(checkpoint_dir)
    data[key] = {
        'ok': bool(max_diff is not None and abs(max_diff) <= tol),
        'max_diff': None if max_diff is None else float(max_diff),
        'checked_at': datetime.now().isoformat(),
    }
    save_parity(checkpoint_dir, data)
    return data[key]


def can_use_incremental(checkpoint_dir, key, param=None, min_len=0, window_bars=720):
    """Итоговое решение: warm-up допустим И паритет подтверждён (или ещё не проверялся).

    Если паритет проверялся и провален — пересчитываем полным прогоном, несмотря
    на формально достаточный warm-up.
    """
    if not incremental_ok(key, param, min_len, window_bars):
        return False
    rec = load_parity(checkpoint_dir).get(key)
    if rec and not rec.get('ok', False):
        return False
    return True


def window_start(end_ts, window_bars, bars_per_hour=1):
    """Начало окна для rolling-метрик: сделки раньше этой точки выпадают.

    end_ts — время последнего бара окна (datetime), window_bars — длина окна в барах.
    """
    if isinstance(end_ts, str):
        end_ts = datetime.fromisoformat(end_ts)
    return end_ts - timedelta(hours=window_bars / float(bars_per_hour or 1))
