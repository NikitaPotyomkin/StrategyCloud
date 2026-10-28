"""Разовая починка main.py после двойного перекодирования.

Что случилось: файл прочитали как «windows-1251-подобную» кодировку и записали
как UTF-8, поэтому русский текст стал «РЎРІРѕР±РѕРґРЅ»-мусором. Преобразование
обратимо: текст → байты → исходный UTF-8 → текст.

Особенность: при таком чтении байты 0x98 (вторая половина «Д», «И», «й») не имеют
буквы в cp1251 и попали в файл как C1-контролы (U+0098). Поэтому кодируем не через
cp1251 целиком, а посимвольно: буква → cp1251, контрол с кодом < 256 → этот байт.

Файл перезаписывается только если проверка прошла. Резерв: main.py.doubleenc.bak.

Запуск:  python fix_main_encoding.py
"""
import shutil
from pathlib import Path

SRC = Path(__file__).with_name('main.py')
BAK = SRC.with_name('main.py.doubleenc.bak')
PROBES = ('Свободных', 'Ночной перерасчёт', 'ШТУРВАЛ', 'Чекпойнты', 'Маркер')
BAD = ('РЎ', 'РІ', 'Рѕ')


def to_source_bytes(text):
    """Обратное преобразование: мусорный текст → исходные байты UTF-8."""
    out = bytearray()
    for ch in text:
        try:
            out += ch.encode('cp1251')
            continue
        except UnicodeEncodeError:
            pass
        code = ord(ch)
        if code < 256:
            out.append(code)        # C1-контролы: U+0098 → байт 0x98
        else:
            out += ch.encode('utf-8')   # не наш случай, но не теряем данные
    return bytes(out)


txt = SRC.read_text(encoding='utf-8')
try:
    fixed = to_source_bytes(txt).decode('utf-8')
except UnicodeDecodeError as exc:
    pos = getattr(exc, 'start', 0) or 0
    print('НЕ ЧИНИТСЯ автоматически:', exc)
    print('Окрестность:', repr(txt[max(0, pos - 40):pos + 40]))
    raise SystemExit(1)

hits = [p for p in PROBES if p in fixed]
leftover = [b for b in BAD if b in fixed]
print(f'Длина: {len(txt)} симв. → {len(fixed)} симв.')
print(f'Найдено осмысленное: {hits}')
if leftover:
    print(f'Остатки мусора: {leftover} — файл НЕ тронут')
    raise SystemExit(2)
if len(hits) < 2:
    print('Проверка не прошла — файл НЕ тронут.')
    raise SystemExit(3)

shutil.copy2(SRC, BAK)
SRC.write_text(fixed, encoding='utf-8')
print(f'Готово: {SRC.name} починен. Резерв: {BAK.name}')
