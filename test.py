import os
import shutil
import logging
import zipfile
import tempfile
import re
from pathlib import Path
from fpdf import FPDF

# ================= НАСТРОЙКИ =================
SOURCE_DIR = r"D:\NIKSON\Документы"
TARGET_DIR_NAME = "Еврохим - документы"
REPORT_FILENAME = "check_list.txt"
ERROR_LOG_FILENAME = "errors.log"

# ================= ПЕРЕЧЕНЬ ДОКУМЕНТОВ =================
DOC_LIST = [
    "Паспорт (первая страница + прописка + ранее выданные)",
    "СНИЛС",
    "Документ об образовании (диплом)",
    "Трудовая книжка (копия) / выписка из ЭТК",
    "Военный билет (все страницы с записями)",
    "ИНН",
    "Банковские реквизиты для ЗП",
    "Свидетельство о заключении брака (при наличии)",
    "Свидетельства о рождении детей (при наличии)",
    "Документы на льготы (при наличии)",
    "Фото на пропуск (jpg/jpeg)"
]

# Пункты, где «НЕТ» заменяется на «НЕ АКТУАЛЬНО»
OPTIONAL_ITEMS = {
    "Свидетельство о заключении брака (при наличии)",
    "Свидетельства о рождении детей (при наличии)",
    "Документы на льготы (при наличии)",
}

# ================= СООТВЕТСТВИЯ (ключи СТРОГО совпадают с DOC_LIST) =================
FILE_MAPPING = {
    "Паспорт (первая страница + прописка + ранее выданные)": ["Сканы паспорта"],
    "СНИЛС": ["СНИЛС"],
    "Документ об образовании (диплом)": ["Диплом.jpg"],
    "Трудовая книжка (копия) / выписка из ЭТК": ["Трудовая", "Трудовая_книжка_Потемкин_H.pdf"],
    "Военный билет (все страницы с записями)": ["Военник"],
    "ИНН": ["ИНН"],
    "Банковские реквизиты для ЗП": ["Сбер Реквизиты.txt"],
    "Фото на пропуск (jpg/jpeg)": ["Фото.jpg"],
}


# ================= ЛОГИРОВАНИЕ =================
def setup_logging(log_path):
    logging.basicConfig(
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()
        ],
        force=True
    )

# ================= ЕСТЕСТВЕННАЯ СОРТИРОВКА =================
def natural_sort_key(path):
    name = str(path)
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', name)]

# ================= ОЧИСТКА ВРЕМЕННОЙ ПАПКИ =================
def clean_temp_dir(temp_dir):
    """Полностью очищает временную папку перед каждым использованием."""
    if temp_dir.exists():
        for item in temp_dir.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
            except Exception as e:
                logging.warning(f"Не удалось удалить {item} из temp: {e}")

# ================= РАБОТА С PDF =================
def create_pdf_from_images(image_paths, output_path):
    """Конвертирует список изображений в один PDF."""
    pdf = FPDF()
    success_count = 0
    for img_path in sorted(image_paths, key=natural_sort_key):
        try:
            if not img_path.exists():
                logging.warning(f"Файл не найден: {img_path}")
                continue
            pdf.add_page()
            pdf.image(str(img_path), x=10, y=10, w=190)
            success_count += 1
        except Exception as e:
            logging.error(f"Не удалось добавить изображение {img_path} в PDF: {e}")
            continue

    if success_count == 0:
        logging.warning(f"Не удалось конвертировать ни одного изображения для: {output_path}")
        return False

    try:
        pdf.output(output_path)
        return True
    except Exception as e:
        logging.error(f"Ошибка при сохранении PDF {output_path}: {e}")
        return False

def get_all_image_files(path):
    """Рекурсивный поиск изображений JPG/JPEG/PNG строго внутри указанной папки."""
    images = []
    if path.is_dir():
        for root, _, files in os.walk(path):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    images.append(Path(root) / file)
    return images

def process_folder_to_pdf(folder_path, output_pdf_path):
    images = get_all_image_files(folder_path)
    if not images:
        logging.info(f"В папке {folder_path} не найдено изображений")
        return False
    return create_pdf_from_images(images, output_pdf_path)


def process_folder_to_pdf(folder_path, output_pdf_path):
    images = get_all_image_files(folder_path)
    if not images:
        logging.info(f"В папке {folder_path} не найдено изображений")
        return False

    # ДИАГНОСТИКА: показываем, что именно собирается в PDF
    print(f"\n--- Файлы для PDF из папки: {folder_path} ---")
    for i, img in enumerate(sorted(images, key=natural_sort_key), 1):
        print(f"  {i}. {img.name}  ({img.parent})")
    print(f"  Всего: {len(images)} файлов\n")

    return create_pdf_from_images(images, output_pdf_path)

def extract_images_from_zip(zip_path, temp_dir):
    """Извлекает только изображения из ZIP в чистую временную папку."""
    clean_temp_dir(temp_dir)  # Принудительная очистка перед распаковкой
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if name.lower().endswith(('.jpg', '.jpeg', '.png')):
                    zf.extract(name, temp_dir)
        return True
    except zipfile.BadZipFile:
        logging.error(f"Повреждённый ZIP-архив: {zip_path}")
        return False
    except Exception as e:
        logging.error(f"Ошибка при распаковке ZIP {zip_path}: {e}")
        return False

def process_zip_to_pdf(zip_path, output_pdf_path, temp_dir):
    if not extract_images_from_zip(zip_path, temp_dir):
        return False
    # Ищем изображения ТОЛЬКО внутри temp_dir
    images = []
    for root, _, files in os.walk(temp_dir):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png')):
                images.append(Path(root) / f)
    if not images:
        logging.warning(f"В архиве {zip_path} не найдено изображений")
        return False
    result = create_pdf_from_images(images, output_pdf_path)
    clean_temp_dir(temp_dir)  # Очистка после использования
    return result

def process_single_image_to_pdf(image_path, output_pdf_path):
    return create_pdf_from_images([image_path], output_pdf_path)

def safe_copy_file(src, dst):
    """Безопасное копирование с логированием."""
    try:
        shutil.copy2(src, dst)
        return True
    except PermissionError:
        logging.error(f"Нет прав на копирование: {src}")
        return False
    except Exception as e:
        logging.error(f"Ошибка при копировании {src}: {e}")
        return False

# ================= ОСНОВНАЯ ЛОГИКА =================
def main():
    source = Path(SOURCE_DIR)
    target = source / TARGET_DIR_NAME

    # Временная папка — в системном %TEMP%, вне исходной директории
    temp_dir = Path(tempfile.gettempdir()) / "euхим_temp"

    # УДАЛЯЕМ СТАРУЮ ПАПКУ ПЕРЕД НАЧАЛОМ
    if target.exists():
        try:
            shutil.rmtree(target)
            print(f"Старая папка удалена: {target}")
        except Exception as e:
            print(f"Не удалось удалить старую папку: {e}")
            return

    # Создаём целевую папку
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Критическая ошибка: не удалось создать целевую папку: {e}")
        return

    # Логирование
    error_log_path = target / ERROR_LOG_FILENAME
    setup_logging(error_log_path)

    # Временная папка
    clean_temp_dir(temp_dir)
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logging.critical(f"Не удалось создать временную папку: {e}")
        return

    # Инициализация статусов
    status = {}
    for doc in DOC_LIST:
        if doc in OPTIONAL_ITEMS:
            status[doc] = "НЕ АКТУАЛЬНО"
        else:
            status[doc] = "НЕТ"

    # Обработка
    for doc_key, items in FILE_MAPPING.items():
        if not items:
            continue

        for item in items:
            item_path = source / item

            if not item_path.exists():
                logging.warning(f"Не найден объект для пункта '{doc_key}': {item}")
                continue

            try:
                if item_path.is_dir():
                    # Папка: все фото внутри → один PDF
                    pdf_name = f"{item}_converted.pdf"
                    pdf_path = target / pdf_name
                    if process_folder_to_pdf(item_path, pdf_path):
                        status[doc_key] = "ЕСТЬ (конвертировано в PDF)"
                        print(f"Папка → PDF: {item} → {pdf_name}")
                    else:
                        if status[doc_key] != "НЕ АКТУАЛЬНО":
                            status[doc_key] = "ЕСТЬ (но конвертация не удалась, см. errors.log)"

                elif item_path.suffix.lower() == '.zip':
                    # ZIP: распаковать в чистый temp, фото → PDF
                    pdf_name = f"{item_path.stem}_converted.pdf"
                    pdf_path = target / pdf_name
                    if process_zip_to_pdf(item_path, pdf_path, temp_dir):
                        status[doc_key] = "ЕСТЬ (из ZIP, конвертировано в PDF)"
                        print(f"ZIP → PDF: {item} → {pdf_name}")
                    else:
                        if status[doc_key] != "НЕ АКТУАЛЬНО":
                            status[doc_key] = "ЕСТЬ (но обработка ZIP не удалась, см. errors.log)"

                elif item_path.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                    # Проверяем: это фото на пропуск или обычный документ?
                    if doc_key == "Фото на пропуск (jpg/jpeg)":
                        # Просто копируем как есть, без конвертации
                        dst_path = target / item_path.name
                        if safe_copy_file(item_path, dst_path):
                            status[doc_key] = "ЕСТЬ (JPG, скопировано как есть)"
                            print(f"Фото скопировано как есть: {item}")
                        else:
                            status[doc_key] = "ЕСТЬ (но копирование не удалось, см. errors.log)"
                    else:
                        # Одиночное фото → PDF (например, Диплом)
                        pdf_name = f"{item_path.stem}_converted.pdf"
                        pdf_path = target / pdf_name
                        if process_single_image_to_pdf(item_path, pdf_path):
                            status[doc_key] = "ЕСТЬ (конвертировано в PDF)"
                            print(f"Фото → PDF: {item} → {pdf_name}")
                        else:
                            if status[doc_key] != "НЕ АКТУАЛЬНО":
                                status[doc_key] = "ЕСТЬ (но конвертация не удалась, см. errors.log)"

                elif item_path.suffix.lower() == '.pdf':
                    # PDF: просто копируем
                    dst_path = target / item_path.name
                    if safe_copy_file(item_path, dst_path):
                        status[doc_key] = "ЕСТЬ (PDF)"
                        print(f"Скопирован PDF: {item}")
                    else:
                        if status[doc_key] != "НЕ АКТУАЛЬНО":
                            status[doc_key] = "ЕСТЬ (но копирование не удалось, см. errors.log)"

                elif item_path.suffix.lower() == '.txt':
                    # Текстовый файл (например, реквизиты): копируем как есть
                    dst_path = target / item_path.name
                    if safe_copy_file(item_path, dst_path):
                        status[doc_key] = "ЕСТЬ (TXT)"
                        print(f"Скопирован TXT: {item}")
                    else:
                        if status[doc_key] != "НЕ АКТУАЛЬНО":
                            status[doc_key] = "ЕСТЬ (но копирование не удалось, см. errors.log)"

                else:
                    # Любой другой файл: копируем
                    dst_path = target / item_path.name
                    if safe_copy_file(item_path, dst_path):
                        status[doc_key] = "ЕСТЬ"
                        print(f"Скопирован файл: {item}")

            except Exception as e:
                logging.critical(f"Непредвиденная ошибка при обработке {item}: {e}")
                if status[doc_key] != "НЕ АКТУАЛЬНО":
                    status[doc_key] = "ЕСТЬ (но произошла ошибка, см. errors.log)"

    # ОТЧЁТ
    report_path = target / REPORT_FILENAME
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("ОТЧЁТ ПО НАЛИЧИЮ ДОКУМЕНТОВ ДЛЯ ТРУДОУСТРОЙСТВА\n")
            f.write("=" * 60 + "\n\n")
            for doc in DOC_LIST:
                f.write(f"{doc}: {status[doc]}\n")
            f.write("\n" + "=" * 60 + "\n")
            f.write("Примечание: изображения конвертированы в PDF.\n")
            f.write("Фото на пропуск оставлено в исходном формате JPG.\n")
            f.write("Ошибки обработки — в файле errors.log\n")
        print(f"\nОтчёт сохранён: {report_path}")
    except Exception as e:
        logging.critical(f"Не удалось создать отчёт: {e}")

    # ОЧИСТКА ВРЕМЕННОЙ ПАПКИ
    clean_temp_dir(temp_dir)
    try:
        temp_dir.rmdir()
    except Exception:
        pass  # Некритично

    print("\nГотово!")
    print(f"Целевая папка: {target}")
    print("\n--- ИТОГОВЫЙ ОТЧЁТ ---")
    for doc in DOC_LIST:
        print(f"  {doc}: {status[doc]}")

if __name__ == "__main__":
    main()
