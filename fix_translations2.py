import re

translations = {
    "uz": {
        "Contract Day": "Shartnoma kuni",
        "Contract Month (spelled)": "Shartnoma oyi (so'z bilan)",
        "Contract Year": "Shartnoma yili",
        "Installment Start Day": "To'lov boshlanish kuni",
        "Installment Start Month (spelled)": "To'lov boshlanish oyi (so'z bilan)",
        "Installment Start Year": "To'lov boshlanish yili"
    },
    "ru": {
        "Contract Day": "День заключения договора",
        "Contract Month (spelled)": "Месяц заключения договора (прописью)",
        "Contract Year": "Год заключения договора",
        "Installment Start Day": "День начала платежей",
        "Installment Start Month (spelled)": "Месяц начала платежей (прописью)",
        "Installment Start Year": "Год начала платежей"
    }
}

for lang, trans_dict in translations.items():
    path = f"/app/locale/{lang}/LC_MESSAGES/django.po"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    for msgid, msgstr in trans_dict.items():
        # First append if not exists
        if f'msgid "{msgid}"' not in content:
            content += f'\n\nmsgid "{msgid}"\nmsgstr "{msgstr}"'
        else:
            # Replace existing (including fuzzy ones)
            pattern = re.compile(rf'(?:#, fuzzy\n)?(?:#\|.*?\n)*msgid "{re.escape(msgid)}"\nmsgstr ".*?"', re.MULTILINE)
            replacement = f'msgid "{msgid}"\nmsgstr "{msgstr}"'
            content, _ = pattern.subn(replacement, content)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
print("PO files patched")
