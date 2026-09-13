nums_and_words = {
    0: 'нол',
    1: 'бир',
    2: 'икки',
    3: 'уч',
    4: 'тўрт',
    5: 'беш',
    6: 'олти',
    7: 'етти',
    8: 'саккиз',
    9: 'тўққиз',
    10: 'ўн',
    20: 'йигирма',
    30: 'ўттиз',
    40: 'қирқ',
    50: 'эллик',
    60: 'олтмиш',
    70: 'етмиш',
    80: 'саксон',
    90: 'тўқсон',
    100: 'юз',
    1000: 'минг',
    1000000: 'миллион',
    1000000000: 'миллиард',
    1000000000000: 'триллион',
    1000000000000000: 'квадриллион',
}

def number_to_words(n):
    """Converts a numerical amount into Uzbek words (Sўм / Тийин)"""
    if n is None:
        return ""
    n = float(n)
    integer_part = int(n)
    fractional_part = round((n - integer_part) * 100)
    
    words = convert_integer_to_words(integer_part) + " сўм"
    if fractional_part > 0:
        words += f" {convert_integer_to_words(fractional_part)} тийин"
    return words


def convert_integer_to_words(n):
    if n == 0:
        return nums_and_words[0]

    parts = []

    if n < 0:
        parts.append('минус')
        n = -n

    for divisor, word in [
        (1000000000000000, 'квадриллион'),
        (1000000000000, 'триллион'),
        (1000000000, 'миллиард'),
        (1000000, 'миллион'),
        (1000, 'минг'),
        (100, 'юз')
    ]:
        if n >= divisor:
            parts.append(f"{convert_integer_to_words(n // divisor)} {word}")
            n %= divisor

    if 10 <= n < 20:
        parts.append(f"{nums_and_words[10]} {nums_and_words[n % 10]}")
        return ' '.join(parts)

    if n >= 20:
        parts.append(nums_and_words[(n // 10) * 10])
        n %= 10

    if n > 0:
        parts.append(nums_and_words[n])

    return ' '.join(parts)
import math

def amount_to_words_ru(amount):
    """
    Converts a numerical amount (Decimal or float) into Russian text for UZS currency.
    e.g. 5190000 -> Пять миллионов сто девяносто тысяч сумов 00 тийин, без НДС
    """
    if amount is None:
        return ""
        
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return ""

    units = ('', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять')
    units_fem = ('', 'одна', 'две', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять')
    teens = ('десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать',
             'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать')
    tens = ('', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят',
            'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто')
    hundreds = ('', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот',
                'шестьсот', 'семьсот', 'восемьсот', 'девятьсот')

    def get_group_words(n, gender='male'):
        words = []
        h = n // 100
        t = (n % 100) // 10
        u = n % 10

        if h > 0:
            words.append(hundreds[h])

        if t == 1:
            words.append(teens[u])
        else:
            if t > 1:
                words.append(tens[t])
            if u > 0:
                if gender == 'female':
                    words.append(units_fem[u])
                else:
                    words.append(units[u])
        return words

    def get_suffix(n, suffixes):
        n = n % 100
        if 11 <= n <= 19:
            return suffixes[2]
        n = n % 10
        if n == 1:
            return suffixes[0]
        if 2 <= n <= 4:
            return suffixes[1]
        return suffixes[2]

    integer_part = int(math.floor(amount))
    fractional_part = int(round((amount - integer_part) * 100))

    if integer_part == 0:
        result_words = ['ноль']
    else:
        result_words = []
        
        # Billions
        b = integer_part // 1000000000
        if b > 0:
            result_words.extend(get_group_words(b, 'male'))
            result_words.append(get_suffix(b, ('миллиард', 'миллиарда', 'миллиардов')))
            integer_part %= 1000000000

        # Millions
        m = integer_part // 1000000
        if m > 0:
            result_words.extend(get_group_words(m, 'male'))
            result_words.append(get_suffix(m, ('миллион', 'миллиона', 'миллионов')))
            integer_part %= 1000000

        # Thousands
        th = integer_part // 1000
        if th > 0:
            result_words.extend(get_group_words(th, 'female'))
            result_words.append(get_suffix(th, ('тысяча', 'тысячи', 'тысяч')))
            integer_part %= 1000

        # Units
        if integer_part > 0:
            result_words.extend(get_group_words(integer_part, 'male'))

    result_str = ' '.join([w for w in result_words if w]).strip()
    
    # Capitalize first letter properly
    if result_str:
        result_str = result_str[0].upper() + result_str[1:]

    # Suffix for original un-modulo'd integer_part
    original_int = int(math.floor(amount))
    sum_suffix = get_suffix(original_int, ('сум', 'сума', 'сумов'))

    return f"{result_str} {sum_suffix} {fractional_part:02d} тийин, без НДС"

MONTHS_RU = {
    1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
    5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
    9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
}
MONTHS_UZ = {
    1: 'январ', 2: 'феврал', 3: 'март', 4: 'апрел',
    5: 'май', 6: 'июн', 7: 'июл', 8: 'август',
    9: 'сентябр', 10: 'октябр', 11: 'ноябр', 12: 'декабр'
}
