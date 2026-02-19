# ==================== БРЕНДЫ И ВАРИАЦИИ ====================

BRAND_GROUPS = [
    {
        "main": "L.G.B.",
        "variations": {
            "latin": ["L.G.B.", "LGB", "Le grand bleu", "Le grande bleu", "Le Grand Bleu",
                      "Legrandbleu", "Le grande blue", "L G B", "L G.B.", "L.G B"],
            "jp": ["ルグランブルー", "ル・グラン・ブルー", "エルジービー"],
            "cn": ["大蓝", "勒格朗蓝", "勒格朗布尔"],
            "universal": ["LGB vintage", "Le grand bleu vintage"]
        }
    },
    {
        "main": "if six was nine",
        "variations": {
            "latin": ["if six was nine", "ifsixwasnine", "if 6 was 9", "if6was9",
                      "Maniac corp", "bedrock", "Maniac Corporation", "Maniac", "Bed Rock"],
            "jp": ["イフシックスワズナイン", "イフ・シックス・ワズ・ナイン"],
            "cn": ["如果六是九", "伊夫西克斯瓦兹奈因"],
            "universal": ["if six was nine vintage", "ifsixwasnine archive"]
        }
    },
    {
        "main": "kmrii",
        "variations": {
            "latin": ["kmrii", "kemuri", "km rii", "km*rii", "km-rii", "km_rii", "KMRII"],
            "jp": ["ケムリ"],
            "cn": ["烟", "凯穆里"],
            "universal": ["kemuri vintage", "kmrii vintage"]
        }
    },
    {
        "main": "14th addiction",
        "variations": {
            "latin": ["14th addiction", "14thaddiction", "14th addition", "14th addict",
                      "14th adiction", "14th addictions", "14th-addiction", "14th_addiction",
                      "Fourteenth addiction"],
            "jp": ["14番目の中毒", "フォーティーンスアディクション"],
            "cn": ["第14瘾", "第十四瘾", "14号瘾", "十四号瘾", "福提恩阿迪克申"],
            "universal": ["14th addiction vintage", "14th archive"]
        }
    },
    {
        "main": "share spirit",
        "variations": {
            "latin": ["share spirit", "sharespirit", "share-spirit", "share_spirit",
                      "share sprit", "share sperit"],
            "jp": ["シェアスピリット", "シェアースピリット"],
            "cn": ["分享精神", "共享精神", "谢尔斯皮里特"],
            "universal": ["share spirit vintage"]
        }
    },
    {
        "main": "gunda",
        "variations": {
            "latin": ["gunda", "ganda"],
            "jp": ["グンダ"],
            "cn": ["贡达", "古恩达"],
            "universal": ["gunda vintage"]
        }
    },
    {
        "main": "yasuyuki ishii",
        "variations": {
            "latin": ["yasuyuki ishii", "yasuyuki-ishii", "yasuyuki_ishii", "yasuyuki ishi"],
            "jp": ["石井康之", "イシイヤスユキ"],
            "cn": ["雅之石井"],
            "universal": ["yasuyuki ishii vintage"]
        }
    },
    {
        "main": "gongen",
        "variations": {
            "latin": ["gongen"],
            "jp": ["権現"],
            "cn": ["权现"],
            "universal": ["gongen vintage"]
        }
    },
    {
        "main": "blaze",
        "variations": {
            "latin": ["blaze", "blaz", "blase"],
            "jp": ["ブレイズ"],
            "cn": ["火焰", "布雷兹"],
            "universal": ["blaze vintage"]
        }
    },
    {
        "main": "shohei takamiya",
        "variations": {
            "latin": ["shohei takamiya", "shoheitakamiya", "shohei_takamiya", "takamiya"],
            "jp": ["高宮翔平", "タカミヤショウヘイ"],
            "cn": ["高宫翔平", "塔卡米亚翔平"],
            "universal": ["shohei takamiya vintage"]
        }
    }
]

# Быстрый доступ к основным именам брендов
BRAND_MAIN_NAMES = [group["main"] for group in BRAND_GROUPS]
POPULAR_BRANDS = BRAND_MAIN_NAMES[:10]

# Список платформ и поддерживаемые языки для парсинга
ALL_PLATFORMS = [
    'Mercari JP',
    'Rakuten Rakuma',
    'Yahoo Flea',
    'Yahoo Auction',
    'Yahoo Shopping',
    'Rakuten Mall',
    'eBay',
    '2nd Street JP'
]

PLATFORM_LANGUAGES = {
    'Mercari JP': ['jp', 'latin', 'universal'],
    'Rakuten Rakuma': ['jp', 'latin', 'universal'],
    'Yahoo Flea': ['jp', 'latin', 'universal'],
    'Yahoo Auction': ['jp', 'latin', 'universal'],
    'Yahoo Shopping': ['jp', 'latin', 'universal'],
    'Rakuten Mall': ['jp', 'latin', 'universal'],
    'eBay': ['latin', 'universal'],
    '2nd Street JP': ['jp', 'latin', 'universal'],
}

# Функции для работы с брендами
def get_variations_for_platform(brand_main, platform):
    """
    Возвращает список всех вариаций бренда для конкретной платформы
    """
    for group in BRAND_GROUPS:
        if group["main"] == brand_main:
            vars_list = []
            needed = PLATFORM_LANGUAGES.get(platform, ['latin', 'universal'])
            for typ in needed:
                if typ in group["variations"]:
                    vars_list.extend(group["variations"][typ])
            return list(dict.fromkeys(vars_list))
    return [brand_main]

def expand_selected_brands_for_platforms(selected_brands, platforms):
    """
    Возвращает словарь: {platform: [вариации выбранных брендов]}
    """
    result = {}
    for p in platforms:
        vars_list = []
        for brand in selected_brands:
            vars_list.extend(get_variations_for_platform(brand, p))
        result[p] = list(dict.fromkeys(vars_list))
    return result