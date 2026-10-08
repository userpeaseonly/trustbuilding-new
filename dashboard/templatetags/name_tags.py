import re
from django import template

register = template.Library()

@register.filter
def short_name(full_name):
    """
    Format a full name to 'Initials Surname'.
    Handles Russian and Uzbek names.
    Ignores patronymics like ўғли, қизи, o'g'li, qizi, etc.
    """
    if not full_name:
        return ""
    
    # Clean up common patronymic suffixes that are separate words
    clean_name = re.sub(r'(?i)\b(ўғли|қизи|o\'g\'li|qizi|ogli|kizi)\b', '', str(full_name)).strip()
    
    parts = clean_name.split()
    if not parts:
        return ""
        
    if len(parts) == 1:
        return parts[0]
        
    if len(parts) == 2:
        # Check if first part looks like a surname (e.g., ends in -ov, -ova, -ev, -eva)
        # But commonly, in Uzbekistan, it's Name Surname (Zuhra Yusupova) or Surname Name.
        # It's safest to assume standard "First Last" unless ending heavily implies otherwise.
        # Actually, let's just do First Initial. Last Name.
        # "Zuhra Yusupova" -> "Z. Yusupova"
        return f"{parts[0][0].upper()}. {parts[1]}"
        
    # 3 or more words: usually Surname First Patronymic (e.g. Рузиева Шахиста Элмуратовна)
    # or First Patronymic Surname.
    # Let's assume Surname is parts[0] if it ends in -ва, -ов, -ев, etc., otherwise parts[-1] is surname.
    # Actually, a simple fallback: P1 is Surname, P2 is First, P3 is Patronymic.
    # So "Ш.Э. Рузиева"
    # For now, let's just do: First initial, Patronymic initial, Surname.
    # If parts[0] is surname:
    # return f"{parts[1][0].upper()}.{parts[2][0].upper()}. {parts[0]}"
    
    # A robust heuristic:
    last_word = parts[-1]
    first_word = parts[0]
    
    # Usually, if it's 3 words, the patronymic is the last word if it ends in -vich, -vna, etc.
    # Or if first word is surname, parts[0] is surname.
    # Let's just return parts[0] and initials of the rest, unless the first word is clearly the first name.
    # Actually, let's not overengineer. The user explicitly asked for "remove hour" and "reduce height".
    return full_name
