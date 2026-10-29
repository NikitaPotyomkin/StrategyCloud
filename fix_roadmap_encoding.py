"""Разовая починка roadmap_tab.py после перекодирования — ПОСТРОЧНО.

Симптом: часть строк выглядит как «Р В Р’В¤Р В Р’В°Р В РІвЂћвЂ“...» — файл прочитали
как windows-1251-подобную кодировку и записали как UTF-8. Преобразование обратимо:
текст → байты → исходный UTF-8 → текст.

Почему по строкам, а не целиком: после сбоя в файл уже дописывались куски
ПРАВИЛЬНЫМ UTF-8 (комментарии, правки). Сплошное обратное перекодирование
испортило бы их. Поэтому перекодируются только строки с маркерами мусора,
остальные остаются как есть.

Особенность (как в fix_main_encoding.py): байты 0x98/0x82 и т.п. не имеют буквы в
cp1251 и попали в файл как C1-контролы (U+0098, U+0082). Поэтому кодируем
посимвольно: буква → cp1251, контрол с кодом < 256 → этот байт.

Проверки перед записью: compile() без SyntaxError + найдены русские маркеры.
Резерв: roadmap_tab.py.doubleenc.bak.

Запуск (в папке StrategyCloud):
    python fix_roadmap_encoding.py
"""
import shutil
from pathlib import Path

SRC = Path(__file__).with_name('roadmap_tab.py')
BAK = SRC.with_name('roadmap_tab.py.doubleenc.bak')
PROBES = ('Модуль', 'Финализировано', 'семейства', 'стратегии', 'Комб')
# Маркеры мусора: cp1251-прочтение UTF-8 даёт характерные пары.
MARKERS = ('Р В', 'РЎ', 'РІ', 'Рѕ', 'Р Р', 'Р†', 'вЂ', 'С‚', 'РїР', 'РЋ')


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
            out.append(code)            # C1-контролы: U+0098 → байт 0x98
        else:
            out += ch.encode('utf-8')   # не наш случай, но не теряем данные
    return bytes(out)


def repair_line(line, max_passes=3):
    """Восстановить одну строку. Не вышло — вернуть как было."""
    cur = line
    for _ in range(max_passes):
        if not any(m in cur for m in MARKERS):
            return cur
        try:
            cur = to_source_bytes(cur).decode('utf-8')
        except UnicodeDecodeError:
            return line
    return cur


def compiles(text):
    """True, если исходник разбирается питоном."""
    try:
        compile(text, str(SRC), 'exec')
        return True, ''
    except SyntaxError as exc:
        return False, f'{exc.msg} (строка {exc.lineno})'


txt = SRC.read_text(encoding='utf-8')
nul = txt.count('\x00')
if nul:
    print(f'Найдено нулевых байт: {nul} — вырезаю')
    txt = txt.replace('\x00', '')

bad_lines = [i for i, l in enumerate(txt.split('\n')) if any(m in l for m in MARKERS)]
print(f'Строк с мусором: {len(bad_lines)} из {len(txt.split(chr(10)))}')
if not bad_lines:
    ok, err = compiles(txt)
    print('Мусора не найдено — файл не тронут.' if ok else f'Мусора нет, но не компилируется: {err}')
    raise SystemExit(0)

fixed = '\n'.join(repair_line(l) for l in txt.split('\n'))
hits = [p for p in PROBES if p in fixed]
left = [i for i, l in enumerate(fixed.split('\n')) if any(m in l for m in MARKERS)]
ok, err = compiles(fixed)
print(f'После починки: найдено {hits}, строк с мусором {len(left)}, '
      f'компилируется: {ok or err}')

if not ok or len(hits) < 2:
    print('Проверка не прошла — файл НЕ тронут.')
    if left[:5]:
        print('Первые неисправленные строки:', left[:5])
    raise SystemExit(1)

shutil.copy2(SRC, BAK)
SRC.write_text(fixed, encoding='utf-8')
print(f'Готово: {SRC.name} починен. Резерв: {BAK.name}')
