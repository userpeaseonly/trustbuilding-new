import re

mapping = {
    # Contract Info
    "Shartnoma_raqami": "Шартнома_рақами",
    "Shartnoma_tuzilgan_sana": "Шартнома_тузилган_сана",
    "Tolov_boshlanish_sanasi": "Тўлов_бошланиш_санаси",
    "Shartnoma_kuni": "Шартнома_бўлган_сана",
    "Shartnoma_oyi": "Шартнома_ойи",
    "Shartnoma_yili": "Шартнома_бўлган_йил",
    "Tolov_kuni": "Тўлов_куни",
    "Tolov_oyi": "Тўлов_ойи",
    "Tolov_yili": "Тўлов_йили",

    # Company Info
    "Pudratchi": "Пудратчи",
    "Kompaniya_rahbari": "Пудратчи_раҳбари",
    "Kompaniya_rahbari_qisqa": "Пудратчи_раҳбари_қисқартмаси",
    "Pudratchi_banki": "Пудратчи_банки",
    "Pudratchi_MFO": "Пудратчи_МФО",
    "Pudratchi_XR": "Пудратчи_ХР",
    "Pudratchi_INN": "Пудратчи_ИНН",
    "Pudratchi_Manzili": "Пудратчи_Манзили",

    # Customer Info
    "Xaridor_FIO": "Сотиб_олувчи_ФИО",
    "Xaridor_FIO_qisqa": "Сотиб_олувчи_ФИО_қисқартмаси",
    "Xaridor_pasporti": "Сотиб_олувчи_паспорт_серияси",
    "Xaridor_PINFL": "Сотиб_олувчи_ПИНФЛ",
    "Pasport_berilgan_sana": "Паспорти_берилган_вақти",
    "Pasport_berilgan_joy": "Паспорт_берилган_жойи",
    "Telefon_raqami": "Телефон_рақами",

    # Building & Property Info
    "Obyekt": "Объект",
    "Kadastr_raqami": "Кадастр_рақами",
    "Topshirish_muddati": "Топшириш_муддати",
    "Yer_maydoni": "Ер_майдони",
    "Qurilish_osti_maydoni": "Қурилиш_ости_майдони",

    # Financials
    "Shartnoma_summasi": "Шартнома_суммаси",
    "Shartnoma_summasi_soz_bilan": "Шартнома_суммаси_сўз_билан",
    "Boshlangich_tolov": "Бошланғич_тўлов",
    "Oylik_tolov": "График_бўйича_ойлик_тўлов",

    # Apartment Info
    "Blok": "Блок_",
    "Podyezd": "Подъезд",
    "Qavat": "Этаж",
    "Kvartira_raqami": "Квартира_рақами",
    "Xonalar_soni": "Яшаш_хоналар_сони",
    "Umumiy_maydon": "Умумий_майдони",
    "Bir_kv_metr_narxi": "M_1_кв_метр_нархи",
    "Bir_kv_metr_narxi_soz_bilan": "M_1_кв_нархи_сўз_билан"
}

path = "contract/templates/contract/template_list.html"
with open(path, "r", encoding="utf-8") as f:
    html = f.read()

for lat, cyr in mapping.items():
    # Find something like: <span class="text-blue-300">«Shartnoma_raqami»</span>
    # and replace with:
    # <div class="flex flex-col"><span class="text-blue-300">«Shartnoma_raqami»</span> <span class="text-blue-300/60 mt-0.5">«Шартнома_рақами»</span></div>
    
    # Or simpler:
    # <span class="text-blue-300">«Shartnoma_raqami» <span class="text-blue-300/60 ml-2">«Шартнома_рақами»</span></span>
    
    # Let's extract the color class dynamically
    pattern = re.compile(rf'(<span class="(text-[a-z]+-[0-9]+)">)«{lat}»</span>')
    
    def replacer(match):
        full_span_start = match.group(1)
        color_class = match.group(2)
        # We append a smaller, dimmer cyrillic string
        return f'{full_span_start}«{lat}» <br><span class="{color_class}/60 text-xs mt-0.5 inline-block">«{cyr}»</span></span>'
        
    html = pattern.sub(replacer, html)

with open(path, "w", encoding="utf-8") as f:
    f.write(html)
print("Cheat sheet updated")
