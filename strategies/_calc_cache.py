"""Свёртка SL/TP: кэш подготовленного df на расчётных функциях семейств.

ПОЧЕМУ ЭТО РАБОТАЕТ
    Сигналы стратегии НЕ зависят от SL/TP. Внутри одной комбинации параметров
    (family, param_key) подготовка признаков (calc_*) одинакова для всех пар
    SL/TP, а пары идут подряд (product(param, SL, TP) — параметр снаружи).
    Значит подготовку достаточно посчитать один раз, а остальные пары (у нас
    9 = 3 SL × 3 TP) обслужить из кэша. Замер (tools/bt_split.py, 22.10.2026):
    расчёт — 47% времени полного прогона корзины, 96 мин из 203.

КАК
    backtest семейства вызывает calc_x(...) как ГЛОБАЛЬНОЕ имя своего модуля,
    поэтому подмена атрибута модуля видна (тот же приём, что в tools/bt_split.py,
    которым это и измерялось). Обёртка считает ключ и, если ключ уже есть,
    возвращает готовый df вместо повторного расчёта.

БЕЗОПАСНОСТЬ
    * В записи кэша хранится ССЫЛКА на исходный df, поэтому id() не может быть
      переиспользован сборщиком мусора, пока запись жива.
    * Ключ включает отпечаток кадра (длина, первый/последний бар, последний close):
      если кадр обновлён НА МЕСТЕ (data_loader.update_symbol_bar дописывает
      закрытый час в тот же объект), попадания не будет — вернётся свежий расчёт.
    * Кэш ничего не меняет: ни df, ни возвращаемое значение calc_*, ни порядок
      вызовов. Он только запоминает уже посчитанное.
    * Если семейство мутирует подготовленный df внутри своей петли, вторая пара
      получит испорченные данные — это тихая ошибка. Ловится паритетом:
          python tools/calc_cache_parity.py
      Без зелёного паритета в прод не включать. Провинившееся семейство
      добавляется в EXCLUDE (полное имя функции) и считается как раньше.
    * Откат в проде — одна строка: config.BacktestConfig.calc_cache = False
      (или переменная окружения STRATEGYCLOUD_CALC_CACHE=0).

ОГРАНИЧЕНИЯ
    * Кэш ключуется на (объект df, аргументы). Он НЕ ускоряет случай, когда кадр
      пересоздаётся на каждую пару (тогда это разные df и кэш не попадёт).
    * Кэш бесполезен там, где подготовка дешева (calc < 10% времени вызова):
      в замере 22.10 таких семейств ~55 из 118 — они и до кэша считаются быстро.
"""
import functools
import importlib
import inspect
import os
import pkgutil
import time

# Имена модульных функций strategies/*, которые считаются «подготовкой».
# Тот же набор, что в tools/bt_split.py, — чтобы замер и оптимизация мерили одно.
PROBE_HINTS = ('calc', 'features', 'prepare', 'compute')

# Полные имена ('strategies.<модуль>.<функция>') семейств, которые кэшировать НЕЛЬЗЯ
# (например, после расхождения в паритете). Пример:
#   EXCLUDE = {'strategies.percentile_reversion.calc_percentile'}
EXCLUDE = set()

MAX_ENTRIES = 3           # сколько подготовленных кадров держим (параметр снаружи → хватает)
_CACHE = {}               # key -> [исходный df (держим ссылку!), результат, сек]
_WRAPPED = set()
_ENABLED = None           # None = решение ещё не принято
_INSTALLED = False
_STATS = {'calls': 0, 'hit': 0, 'miss': 0, 'sec_saved': 0.0, 'sec_miss': 0.0}


# ═══ Флаг включения ═══
def _resolve_enabled(cfg=None):
    """True/False: аргумент → переменная окружения → config → True."""
    if cfg is not None:
        return bool(getattr(cfg, 'calc_cache', True))
    env = os.environ.get('STRATEGYCLOUD_CALC_CACHE')
    if env is not None:
        return env.strip() not in ('0', 'false', 'False', 'no', 'off', '')
    try:
        from config import build_default_configs
        return bool(getattr(build_default_configs().backtest_config, 'calc_cache', True))
    except Exception:
        return True


def set_enabled(flag):
    """Переключить кэш без переустановки обёрток (нужно паритету)."""
    global _ENABLED
    _ENABLED = bool(flag)
    if _ENABLED:
        clear()
    return _ENABLED


def is_enabled():
    return bool(_ENABLED)


def clear():
    _CACHE.clear()


def _fingerprint(df):
    """Отпечаток кадра: ловит правку последнего бара НА МЕСТЕ."""
    n = len(df)
    idx = df.index
    first = idx[0]
    last = idx[-1]
    try:
        last_close = float(df['close'].iloc[-1])
    except Exception:
        last_close = None
    return (n, getattr(first, 'value', first), getattr(last, 'value', last), last_close)


def _key(df, module_name, args):
    return (id(df), module_name, args, _fingerprint(df))


# ═══ Обёртка ═══
def _wrap(module, name, fn, stats):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        if not _ENABLED or not a:
            return fn(*a, **kw)
        df = a[0]
        rest = a[1:]
        stats['calls'] += 1
        try:
            key = _key(df, module.__name__, rest)
        except TypeError:                      # несериализуемые аргументы — не кэшируем
            return fn(*a, **kw)
        ent = _CACHE.get(key)
        if ent is not None and ent[0] is df:
            stats['hit'] += 1
            stats['sec_saved'] += ent[2]
            return ent[1]
        t0 = time.perf_counter()
        out = fn(*a, **kw)
        dt = time.perf_counter() - t0
        stats['miss'] += 1
        stats['sec_miss'] += dt
        if len(_CACHE) >= MAX_ENTRIES:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = [df, out, dt]
        return out

    wrapper._calc_cache_wrapped = True
    wrapper._calc_cache_src = fn
    return wrapper


def _install_probes(stats):
    """Обернуть модульные calc-функции strategies/* (вложенные считаются один раз)."""
    import strategies
    n = 0
    for info in pkgutil.iter_modules(list(strategies.__path__)):
        mod_name = info.name
        if mod_name.startswith('_'):           # служебные модули (_bt_core, _registry…)
            continue
        try:
            mod = importlib.import_module(f'strategies.{mod_name}')
        except Exception:
            continue
        for attr in list(vars(mod)):
            fn = getattr(mod, attr, None)
            if not inspect.isfunction(fn):
                continue
            if not any(h in attr.lower() for h in PROBE_HINTS):
                continue
            full = f'{mod.__name__}.{attr}'
            if full in EXCLUDE or full in _WRAPPED:
                continue
            _WRAPPED.add(full)
            setattr(mod, attr, _wrap(mod, attr, fn, stats))
            n += 1
    return n


def install(enabled=None, cfg=None, verbose=True):
    """Установить кэш (идемпотентно). Вызывается в каждом процессе отдельно."""
    global _INSTALLED, _ENABLED
    if enabled is None:
        enabled = _resolve_enabled(cfg)
    _ENABLED = bool(enabled)
    if _INSTALLED:
        if False and verbose:  # повторная установка — молча (иначе строка на каждый символ)
            print(f'[calc-cache] {"ВКЛЮЧЁН" if _ENABLED else "выключен"} (обёртки уже стоят)',
                  flush=True)
        return len(_WRAPPED)
    n = _install_probes(_STATS)
    _INSTALLED = True
    if verbose:
        if _ENABLED:
            print(f'[calc-cache] ВКЛЮЧЁН: {n} расчётных функций, кэш на {MAX_ENTRIES} ключа — '
                  f'подготовка считается 1 раз на все пары SL/TP', flush=True)
        else:
            print('[calc-cache] выключен (backtest_config.calc_cache=False) — '
                  'расчёт на каждую пару, как раньше', flush=True)
    return n


# ═══ Статистика ═══
def stats():
    return dict(_STATS)


def reset_stats():
    for k in _STATS:
        _STATS[k] = 0.0 if isinstance(_STATS[k], float) else 0


def log_stats(tag='', verbose=True):
    """Напечатать попадания/промахи и оценку сэкономленного времени."""
    hit, miss = _STATS['hit'], _STATS['miss']
    saved = _STATS['sec_saved']
    if verbose:
        head = f'[calc-cache] {tag}:' if tag else '[calc-cache]'
        print(f'{head} попаданий {hit}, промахов {miss}, '
              f'сэкономлено ~{saved:.1f} с ({saved / 60.0:.1f} мин)', flush=True)
    return {'hit': hit, 'miss': miss, 'sec_saved': saved}
