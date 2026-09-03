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
