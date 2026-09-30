import re

translations = {
    "uz": {
        "Contract ID": "Shartnoma ID"
    },
    "ru": {
        "Contract ID": "ID договора"
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
