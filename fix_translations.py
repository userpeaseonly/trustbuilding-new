import os
import re

translations = {
    "Advanced: Excel Import": {
        "ru": "Расширенный: Импорт из Excel",
        "uz": "Kengaytirilgan: Excel-dan import"
    },
    "Download a template, customize apartment details, and upload it back.": {
        "ru": "Скачайте шаблон, заполните данные о квартирах и загрузите его обратно.",
        "uz": "Shablonni yuklab oling, kvartira ma'lumotlarini to'ldiring va uni qayta yuklang."
    },
    "Download Template": {
        "ru": "Скачать шаблон",
        "uz": "Shablonni yuklab olish"
    },
    "Upload Customized Excel": {
        "ru": "Загрузить заполненный Excel",
        "uz": "To'ldirilgan Excelni yuklash"
    },
    "apartments parsed": {
        "ru": "квартир обработано",
        "uz": "kvartira tahlil qilindi"
    },
    "Showing first 5 rows": {
        "ru": "Показаны первые 5 строк",
        "uz": "Dastlabki 5 qator ko'rsatilmoqda"
    },
    "Ent": {
        "ru": "Подъезд",
        "uz": "Podyezd"
    },
    "Floor": {
        "ru": "Этаж",
        "uz": "Qavat"
    },
    "Apt #": {
        "ru": "Кв №",
        "uz": "Kv #"
    },
    "Area": {
        "ru": "Площадь",
        "uz": "Maydoni"
    },
    "Rooms": {
        "ru": "Комнаты",
        "uz": "Xonalar"
    },
    "Automated Grid:": {
        "ru": "Автоматическая сетка:",
        "uz": "Avtomatik to'r:"
    },
    "If no Excel is uploaded, an entrance-by-floor matrix will be automatically generated.": {
        "ru": "Если Excel не загружен, матрица подъездов и этажей будет сгенерирована автоматически.",
        "uz": "Agar Excel yuklanmasa, podyezd va qavatlar matritsasi avtomatik ravishda yaratiladi."
    },
    "Invalid template structure. Missing required columns.": {
        "ru": "Неверная структура шаблона. Отсутствуют обязательные столбцы.",
        "uz": "Noto'g'ri shablon tuzilishi. Majburiy ustunlar yo'q."
    },
    "Failed to parse Excel file.": {
        "ru": "Не удалось прочитать файл Excel.",
        "uz": "Excel faylini o'qishda xatolik yuz berdi."
    },
    "Generate Building Project": {
        "ru": "Создать проект здания",
        "uz": "Bino loyihasini yaratish"
    },
    "New Building Project": {
        "ru": "Новый проект здания",
        "uz": "Yangi bino loyihasi"
    },
    "Define structural parameters to auto-generate the apartment matrix": {
        "ru": "Задайте структурные параметры для автогенерации сетки квартир",
        "uz": "Kvartiralar to'rini avtomatik yaratish uchun tuzilmaviy parametrlarni kiriting"
    }
}

for lang in ["ru", "uz"]:
    po_path = f"locale/{lang}/LC_MESSAGES/django.po"
    with open(po_path, 'r', encoding='utf-8') as f:
        content = f.read()

    for msgid, trans in translations.items():
        # regex to find msgid and replace the following msgstr
        pattern = re.compile(r'msgid "' + re.escape(msgid) + r'"\nmsgstr ".*?"', re.DOTALL)
        replacement = f'msgid "{msgid}"\nmsgstr "{trans[lang]}"'
        
        # If it exists and matches
        if pattern.search(content):
            content = pattern.sub(replacement, content)
        else:
            # Maybe it doesn't exist? append it
            print(f"Adding {msgid} to {lang}")
            content += f'\n\nmsgid "{msgid}"\nmsgstr "{trans[lang]}"\n'

    with open(po_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
print("PO files updated successfully!")
