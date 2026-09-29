import re

translations = {
    "uz": {
        "Date Contract Made": "Shartnoma tuzilgan sana",
        "Installment Start Date": "To'lov boshlanish sanasi",
        "Date Contract Made (DD.MM.YYYY)": "Shartnoma tuzilgan sana (KK.OO.YYYY)",
        "Installment Start Date (DD.MM.YYYY)": "To'lov boshlanish sanasi (KK.OO.YYYY)",
        "Company Name": "Kompaniya nomi",
        "Bank Name & Branch": "Bank nomi va filiali",
        "Bank MFO": "Bank MFO",
        "Account Number (x/r)": "Hisob raqami (x/r)",
        "INN (STIR)": "INN (STIR)",
        "Company Address": "Kompaniya manzili",
        "PINFL (JSHSHR)": "PINFL (JSHSHR)",
        "Building Name": "Obyekt nomi",
        "Cadastre Number": "Kadastr raqami",
        "Delivery Date": "Topshirish muddati",
        "Land Area (sqm)": "Yer maydoni (kv.m)",
        "Const. Footprint (sqm)": "Qurilish osti maydoni (kv.m)"
    },
    "ru": {
        "Date Contract Made": "Дата заключения договора",
        "Installment Start Date": "Дата начала платежей",
        "Date Contract Made (DD.MM.YYYY)": "Дата заключения договора (ДД.ММ.ГГГГ)",
        "Installment Start Date (DD.MM.YYYY)": "Дата начала платежей (ДД.ММ.ГГГГ)",
        "Company Name": "Название компании",
        "Bank Name & Branch": "Название банка и филиал",
        "Bank MFO": "МФО банка",
        "Account Number (x/r)": "Расчетный счет (х/р)",
        "INN (STIR)": "ИНН (СТИР)",
        "Company Address": "Адрес компании",
        "PINFL (JSHSHR)": "ПИНФЛ (ЖШШИР)",
        "Building Name": "Название объекта",
        "Cadastre Number": "Кадастровый номер",
        "Delivery Date": "Дата сдачи",
        "Land Area (sqm)": "Площадь земли (кв.м)",
        "Const. Footprint (sqm)": "Площадь застройки (кв.м)"
    }
}

for lang, trans_dict in translations.items():
    path = f"/app/locale/{lang}/LC_MESSAGES/django.po"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    for msgid, msgstr in trans_dict.items():
        # Regex to find the block for the msgid
        pattern = re.compile(rf'(?:#, fuzzy\n)?(?:#\|.*?\n)*msgid "{re.escape(msgid)}"\nmsgstr ".*?"', re.MULTILINE)
        replacement = f'msgid "{msgid}"\nmsgstr "{msgstr}"'
        content, count = pattern.subn(replacement, content)
        if count == 0:
            # If not found, just append it
            content += f'\n\nmsgid "{msgid}"\nmsgstr "{msgstr}"'

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
print("PO files patched")
