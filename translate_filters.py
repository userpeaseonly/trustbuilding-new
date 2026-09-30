import re

translations = {
    "uz": {
        "All Statuses": "Barcha holatlar",
        "Newest First": "Yangi qo'shilganlar oldin",
        "Oldest First": "Eski qo'shilganlar oldin",
        "Amount: High to Low": "Summa: Kattadan kichikga",
        "Amount: Low to High": "Summa: Kichikdan kattaga"
    },
    "ru": {
        "All Statuses": "Все статусы",
        "Newest First": "Сначала новые",
        "Oldest First": "Сначала старые",
        "Amount: High to Low": "Сумма: По убыванию",
        "Amount: Low to High": "Сумма: По возрастанию"
    }
}

for lang, trans_dict in translations.items():
    path = f"/app/locale/{lang}/LC_MESSAGES/django.po"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    for msgid, msgstr in trans_dict.items():
        if f'msgid "{msgid}"' not in content:
            content += f'\n\nmsgid "{msgid}"\nmsgstr "{msgstr}"'
        else:
            pattern = re.compile(rf'(?:#, fuzzy\n)?(?:#\|.*?\n)*msgid "{re.escape(msgid)}"\nmsgstr ".*?"', re.MULTILINE)
            replacement = f'msgid "{msgid}"\nmsgstr "{msgstr}"'
            content, _ = pattern.subn(replacement, content)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
print("PO files patched")
