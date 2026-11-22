"""P3-аудит: у каких стратегий live-входы расходятся с бэктестом.

Проблема: standalone-модули в backtest() обычно передают _bt_core.state_entry,
то есть «curr == 1 и prev != 1» — разворот -1 -> +1 считается входом. А live
(build_live_specs) берёт модульный check_entry, который часто строгий
(prev == 0), и разворот пропускается. Для value-cross стратегий check_entry —
это порог по непрерывной величине 'k', и подменять его на state_entry нельзя.

Скрипт смотрит по каждому ключу реестра:
  * использует ли его backtest() state_entry (по исходнику функции);
  * как ведёт себя модульный check_entry на парах (0,1), (0,-1), (-1,1), (1,-1).

Только чтение. Запуск: python tools/entry_semantics_audit.py
"""
import inspect
import io
import os
import sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def _call(fn, prev, curr):
    try:
        with redirect_stdout(io.StringIO()):
            return fn(prev, curr)
    except Exception as exc:  # noqa: BLE001 — чужая функция, ловим всё
        return f'<ошибка {type(exc).__name__}>'


def main():
    from strategies import _registry as r

    state_keys, strict_state, value_cross, other = [], [], [], []
    for key in sorted(r.REGISTRY):
        entry = r.REGISTRY[key]
        mod = r._module(entry['module'])
        try:
            src = inspect.getsource(mod.backtest)
        except Exception:  # noqa: BLE001
            src = ''
        uses_state = 'state_entry' in src

        fn = getattr(mod, entry['entry'], None)
        if fn is None:
            other.append((key, 'нет entry-функции'))
            continue
        r01 = _call(fn, 0, 1)
        r0m1 = _call(fn, 0, -1)
        rm11 = _call(fn, -1, 1)
        r1m1 = _call(fn, 1, -1)

        if uses_state:
            state_keys.append(key)
            if r01 == 'long' and r0m1 == 'short':
                if rm11 is None or r1m1 is None:
                    strict_state.append(key)
            else:
                other.append((key, f'state-семантика, но check_entry даёт '
                                    f'(0,1)->{r01}, (0,-1)->{r0m1}'))
        else:
            if r01 == 'long' and r0m1 == 'short' and rm11 is not None:
                value_cross.append(key)
            else:
                other.append((key, f'не state и не «строгий state»: '
                                    f'(0,1)->{r01}, (0,-1)->{r0m1}, (-1,1)->{rm11}'))

    total = len(r.REGISTRY)
    print(f"ключей в реестре: {total}")
    print(f"backtest использует state_entry: {len(state_keys)}")
    print(f"  из них live пропускает разворот -1 -> +1: {len(strict_state)}")
    print(f"check_entry как value-cross (реагирует на любой знак): {len(value_cross)}")
    print(f"прочее/неясное: {len(other)}")

    if strict_state:
        print("\n[РАСХОЖДЕНИЕ live vs backtest] — разворот пропускается:")
        for key in strict_state:
            print(f"  {key}")
    if other:
        print("\n[ТРЕБУЕТ РУЧНОГО РАЗБОРА]:")
        for key, why in other:
            print(f"  {key}: {why}")
    if value_cross:
        print("\n[value-cross, трогать нельзя]: " + ', '.join(value_cross))


if __name__ == '__main__':
    main()
