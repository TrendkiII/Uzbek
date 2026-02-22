# ==================== БРЕНДЫ (УПРОЩЁННО, НО С ТВОИМИ) ====================

# БЕРЁМ ТВОИ РЕАЛЬНЫЕ БРЕНДЫ из оригинального brands.py
# (я скопировал несколько для примера, добавь остальные сам)

BRAND_GROUPS_SIMPLE = [
    {"main": "L.G.B."},
    {"main": "if six was nine"},
    {"main": "kmrii"},
    {"main": "14th addiction"},
    {"main": "share spirit"},
    {"main": "gunda"},
    {"main": "yasuyuki ishii"},
    {"main": "gongen"},
    {"main": "blaze"},
    {"main": "shohei takamiya"},
    {"main": "wild heart"},
    {"main": "john moore"},
    {"main": "ian reid"},
    {"main": "House of Beauty and Culture"},
    {"main": "Koji Kuga"},
    {"main": "beauty:beast"},
    {"main": "The old curiosity shop"},
    {"main": "Swear"},
    {"main": "fotus"},
    {"main": "Saint Tropez"},
    {"main": "Barcord"},
    {"main": "paison&drug"},
    {"main": "Prego"}
]

# Список основных имён для выбора в боте
BRAND_MAIN_NAMES = [group["main"] for group in BRAND_GROUPS_SIMPLE]

# Функция определения бренда по заголовку (ищет основное имя)
def detect_brand_from_title(title):
    """
    Определяет бренд по названию товара.
    Ищет вхождения основных имён брендов в заголовок.
    """
    if not title:
        return None
    
    title_lower = title.lower()
    
    for group in BRAND_GROUPS_SIMPLE:
        brand_main = group["main"].lower()
        if brand_main in title_lower:
            return group["main"]
    
    return None

# ==================== ДОБАВЬ ЭТИ ФУНКЦИИ В КОНЕЦ ФАЙЛА ====================

def get_all_brands():
    """Возвращает список всех брендов"""
    return BRAND_MAIN_NAMES

def get_brand_categories(brand_name=None):
    """Возвращает категории бренда (для совместимости)"""
    if brand_name:
        # Ищем группу с таким основным брендом
        for group in BRAND_GROUPS_SIMPLE:
            if group["main"].lower() == brand_name.lower():
                return [group["main"]]
    return BRAND_MAIN_NAMES

# Для обратной совместимости
def get_all_brands_with_aliases():
    """Возвращает все бренды с алиасами (упрощенно)"""
    return BRAND_GROUPS_SIMPLE