import requests
from bs4 import BeautifulSoup
import json
import time
import random
import os
import schedule
from fake_useragent import UserAgent
from flask import Flask, request
from threading import Thread, Lock
import hashlib
import re
from urllib.parse import quote, urljoin
from datetime import datetime
import sys
import logging

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================
FOUND_ITEMS_FILE = "found_items.json"
CHECK_INTERVAL_MINUTES = 30
REQUEST_TIMEOUT = 30  # Увеличил таймаут
MAX_RETRIES = 5       # Увеличил количество попыток
RETRY_DELAY = 10      # Увеличил задержку между попытками

# Время старта бота для защиты от ранних проверок
BOT_START_TIME = time.time()

# Кеширование User-Agent
ua = UserAgent()
USER_AGENTS = [ua.random for _ in range(20)]  # Увеличил количество UA
UA_INDEX = 0

PROXY = os.environ.get('PROXY_URL', None)

# Блокировки для потокобезопасности
file_lock = Lock()
state_lock = Lock()

# ==================== РАСШИРЕННЫЙ СПИСОК БРЕНДОВ ====================
BRAND_GROUPS = [
    {
        "main": "L.G.B.",
        "variations": [
            "L.G.B.", "LGB", "Le grand bleu", "Le grande bleu", "Le Grand Bleu",
            "Legrandbleu", "Le grande blue", "L G B", "L G.B.", "L.G B",
            "ルグランブルー", "ル・グラン・ブルー", "エルジービー",
            "大蓝", "勒格朗蓝", "勒格朗布尔",
            "Le grand blue", "Legrandblue", "Le grande bleue",
            "LGB vintage", "Le grand bleu vintage"
        ]
    },
    {
        "main": "if six was nine",
        "variations": [
            "if six was nine", "ifsixwasnine", "if 6 was 9", "if6was9",
            "Maniac corp", "bedrock", "Maniac Corporation", "Maniac", "Bed Rock",
            "if six was 9", "maniac corporation", "if six was nin",
            "イフシックスワズナイン", "イフ・シックス・ワズ・ナイン",
            "如果六是九", "伊夫西克斯瓦兹奈因",
            "ifsix", "bedrock vintage", "maniac vintage",
            "if six was nine vintage", "ifsixwasnine archive"
        ]
    },
    {
        "main": "kmrii",
        "variations": [
            "kmrii", "kemuri", "km rii", "km*rii", "km-rii", "km_rii",
            "KMRII", "Kemuri", "KM RII", "kmri", "kmr ii",
            "ケムリ", "烟", "凯穆里",
            "kemuri vintage", "kmrii vintage", "km rii vintage", "km-rii vintage"
        ]
    },
    {
        "main": "14th addiction",
        "variations": [
            "14th addiction", "14thaddiction", "14th addition", "14th addict",
            "14th adiction", "14th addictions", "14th-addiction", "14th_addiction",
            "Fourteenth addiction", "14th Addiction",
            "14th addicition", "14th additction", "14th addikt",
            "14番目の中毒", "フォーティーンスアディクション",
            "第14瘾", "第十四瘾", "14号瘾", "十四号瘾", "福提恩阿迪克申",
            "14th addiction vintage", "14th addict vintage", "14th archive"
        ]
    },
    {
        "main": "share spirit",
        "variations": [
            "share spirit", "sharespirit", "share-spirit", "share_spirit",
            "share sprit", "share sperit", "Share Spirit",
            "share spirrit", "share spirit vintage", "sharespirit vintage",
            "シェアスピリット", "シェアースピリット",
            "分享精神", "共享精神", "谢尔斯皮里特"
        ]
    },
    {
        "main": "gunda",
        "variations": [
            "gunda", "ganda", "Gunda", "gunda vintage",
            "グンダ", "贡达", "古恩达", "gunda archive"
        ]
    },
    {
        "main": "yasuyuki ishii",
        "variations": [
            "yasuyuki ishii", "yasuyuki-ishii", "yasuyuki_ishii", "yasuyuki ishi",
            "Yasuyuki Ishii", "y ishii", "yasuyuki",
            "石井康之", "イシイヤスユキ", "雅之石井",
            "yasuyuki ishii vintage"
        ]
    },
    {
        "main": "gongen",
        "variations": [
            "gongen", "Gongen", "gongen vintage",
            "権現", "权现", "gongen archive"
        ]
    },
    {
        "main": "blaze",
        "variations": [
            "blaze", "blaz", "blase", "Blaze",
            "ブレイズ", "火焰", "布雷兹",
            "blaze vintage", "blaze archive"
        ]
    },
    {
        "main": "shohei takamiya",
        "variations": [
            "shohei takamiya", "shoheitakamiya", "shohei_takamiya",
            "Shohei Takamiya", "takamiya",
            "高宮翔平", "タカミヤショウヘイ", "高宫翔平", "塔卡米亚翔平",
            "shohei takamiya vintage"
        ]
    },
    {
        "main": "wild heart",
        "variations": [
            "wild heart", "wildheart", "wild-heart", "wild_heart",
            "wild hart", "wild hеart", "Wild Heart",
            "ワイルドハート", "野性之心", "狂野之心", "怀尔德哈特",
            "wild heart vintage", "wildheart vintage"
        ]
    },
    {
        "main": "john moore",
        "variations": [
            "john moore", "johnmoore", "john-moore", "john_moore",
            "john moor", "john more", "John Moore",
            "ジョンムーア", "约翰摩尔",
            "john moore vintage", "john moore archive"
        ]
    },
    {
        "main": "ian reid",
        "variations": [
            "ian reid", "ian reed", "ian-reid", "ian_reed",
            "ianreed", "ian read", "Ian Reid", "Ian Reed",
            "イアンリード", "伊恩里德", "伊恩瑞德",
            "ian reid vintage", "ian reed vintage"
        ]
    },
    {
        "main": "House of Beauty and Culture",
        "variations": [
            "House of Beauty and Culture", "HBC", "Hobac",
            "House of Beauty & Culture", "House of Beauty and Cultur",
            "The House of Beauty and Culture", "H.O.B.A.C.",
            "House Of Beauty And Culture", "HOBAC",
            "ハウスオブビューティアンドカルチャー", "美丽文化之家", "霍巴克",
            "HBC vintage", "hobac vintage"
        ]
    },
    {
        "main": "Koji Kuga",
        "variations": [
            "Koji Kuga", "kouji kuga", "koji kuga", "koga koji",
            "久賀浩司", "クガコウジ", "久我浩二", "コージクガ", "久贺浩司", "库加科吉",
            "koji kuga vintage"
        ]
    },
    {
        "main": "beauty:beast",
        "variations": [
            "beauty:beast", "beauty beast", "beauty-beast", "beauty_beast",
            "beauty best", "beauty beaast", "beauty & beast", "beauty and beast",
            "Beauty:Beast", "beautybeast",
            "ビューティービースト", "美女与野兽", "比蒂比斯特",
            "beauty beast vintage"
        ]
    },
    {
        "main": "The old curiosity shop",
        "variations": [
            "The old curiosity shop", "Old Curiosity Shop", "The Old Curiosity Shop",
            "Old Curiosity", "Curiosity Shop",
            "Daita Kimura", "DaitaKimura",
            "木村大汰", "オールドキュリオシティーショップ", "古老奇趣店", "代田木村",
            "old curiocity shop", "curiosty shop",
            "the old curiosity shop vintage", "daita kimura vintage",
            "OCS", "TOCS"
        ]
    },
    {
        "main": "Swear",
        "variations": [
            "Swear", "Swear London", "Swear Alternative",
            "Swear-Alternative", "Swear_Alternative", "Sweat", "Swar",
            "swear london", "swear alternative",
            "スウェア", "スウェアロンドン", "宣誓", "斯维尔",
            "swear vintage", "swear london vintage"
        ]
    },
    {
        "main": "fotus",
        "variations": [
            "fotus", "FÖTUS", "Fötus", "Foetus",
            "Spuren", "spüren", "fotos", "Spure",
            "フォタス", "フェトウス", "福图斯", "斯普伦",
            "fotus vintage", "foetus vintage"
        ]
    },
    {
        "main": "Saint Tropez",
        "variations": [
            "Saint Tropez", "SaintTropez", "Saint-Tropez", "Saint_Tropez",
            "St Tropez", "Saint Tropaz", "ST. Tropez",
            "サン・トロペ", "圣特罗佩",
            "saint tropez vintage"
        ]
    },
    {
        "main": "Barcord",
        "variations": [
            "Barcord", "Barcode", "Bar code", "Bar-code", "Barcorde",
            "バーコード", "条形码", "巴科德",
            "barcord vintage", "barcode vintage"
        ]
    },
    {
        "main": "paison&drug",
        "variations": [
            "paison&drug", "python&drug", "paison and drug", "python and drug",
            "paison & drug", "python & drug", "poison&drug", "pyson&drug",
            "Paison&Drug",
            "パイソン&ドラッグ", "派森与毒", "派森和药",
            "paison drug vintage"
        ]
    },
    {
        "main": "Prego",
        "variations": [
            "Prego", "Prego Uomo", "Prego-Uomo", "Prego_Uomo",
            "Prigo", "prego uomo",
            "プレゴ", "普雷戈", "普雷戈乌莫",
            "prego vintage", "prego uomo vintage"
        ]
    }
]

# ==================== ПЛОСКИЕ СПИСКИ ====================
ALL_BRAND_VARIATIONS = []
BRAND_MAIN_NAMES = []

for group in BRAND_GROUPS:
    BRAND_MAIN_NAMES.append(group["main"])
    for var in group["variations"]:
        if var not in ALL_BRAND_VARIATIONS:
            ALL_BRAND_VARIATIONS.append(var)

POPULAR_BRANDS = BRAND_MAIN_NAMES[:10]

# ==================== СОСТОЯНИЕ БОТА ====================
bot_state = {
    'mode': 'auto',
    'selected_brands': [],
    'last_check': None,
    'is_checking': False,
    'stats': {'total_checks': 0, 'total_finds': 0},
    'interval': CHECK_INTERVAL_MINUTES,
    'paused': False,
    'shutdown': False
}

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def load_found_items():
    try:
        with open(FOUND_ITEMS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_found_items(items):
    try:
        with file_lock:
            with open(FOUND_ITEMS_FILE, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")

def generate_item_id(item):
    unique = f"{item['source']}_{item['url']}_{item['title']}"
    return hashlib.md5(unique.encode('utf-8')).hexdigest()

def get_brand_variations(main_brand):
    for group in BRAND_GROUPS:
        if group["main"] == main_brand:
            return group["variations"]
    return [main_brand]

def expand_selected_brands():
    variations = []
    for brand in bot_state['selected_brands']:
        variations.extend(get_brand_variations(brand))
    return list(dict.fromkeys(variations))

def get_next_user_agent():
    global UA_INDEX
    ua = USER_AGENTS[UA_INDEX % len(USER_AGENTS)]
    UA_INDEX += 1
    return ua

# ==================== TELEGRAM ====================
def send_telegram_message(text, photo_url=None, keyboard=None):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    if not token:
        logger.error("Ошибка: нет TELEGRAM_BOT_TOKEN в Secrets")
        return False

    try:
        if photo_url and chat_id:
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            payload = {
                'chat_id': chat_id,
                'photo': photo_url,
                'caption': text,
                'parse_mode': 'HTML'
            }
            if keyboard:
                payload['reply_markup'] = json.dumps(keyboard)
            requests.post(url, data=payload, timeout=10)
        elif chat_id:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            }
            if keyboard:
                payload['reply_markup'] = json.dumps(keyboard)
            requests.post(url, data=payload, timeout=10)
        else:
            logger.info(f"Сообщение (не отправлено, нет chat_id): {text[:50]}...")
        return True
    except Exception as e:
        logger.error(f"Ошибка Telegram: {e}")
        return False

# ==================== МЕНЮ ====================
def send_main_menu(chat_id=None):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🚀 Запустить проверку", "callback_data": "start_check"}],
            [{"text": "⚙️ Режим работы", "callback_data": "mode_menu"}],
            [{"text": "📊 Статистика", "callback_data": "stats"}],
            [{"text": "📋 Список брендов", "callback_data": "brands_list"}],
            [{"text": "⏱ Интервал", "callback_data": "interval"}],
            [{"text": "🔄 Выбрать бренды", "callback_data": "select_brands_menu"}],
            [{"text": "⏸ Пауза / ▶️ Продолжить", "callback_data": "toggle_pause"}]
        ]
    }

    if bot_state['selected_brands']:
        info = f"Выбрано: {len(bot_state['selected_brands'])} брендов"
    else:
        info = "Бренды не выбраны"
    pause_status = "⏸ ПАУЗА" if bot_state['paused'] else "▶️ АКТИВЕН"
    msg = f"""🤖 <b>Мониторинг</b>

Режим: {bot_state['mode']}
Статус: {pause_status}
{info}
Проверок: {bot_state['stats']['total_checks']}
Найдено: {bot_state['stats']['total_finds']}
Последняя: {bot_state['last_check'] or 'никогда'}
"""
    send_telegram_message(msg, keyboard=keyboard)

def send_mode_menu(chat_id=None):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🤖 Авто (все вариации)", "callback_data": "mode_auto"}],
            [{"text": "👆 Ручной (выбранные)", "callback_data": "mode_manual"}],
            [{"text": "◀️ Назад", "callback_data": "main_menu"}]
        ]
    }
    send_telegram_message("⚙️ Выберите режим:", keyboard=keyboard)

def send_brands_list(page=0, chat_id=None):
    per_page = 8
    start = page * per_page
    end = start + per_page
    total = len(BRAND_MAIN_NAMES)
    pages = (total + per_page - 1) // per_page
    slice_names = BRAND_MAIN_NAMES[start:end]

    keyboard = {"inline_keyboard": []}
    for name in slice_names:
        mark = "✅ " if name in bot_state['selected_brands'] else ""
        keyboard["inline_keyboard"].append([
            {"text": f"{mark}{name}", "callback_data": f"toggle_{name}"}
        ])

    nav = []
    if page > 0:
        nav.append({"text": "◀️", "callback_data": f"page_{page-1}"})
    nav.append({"text": f"{page+1}/{pages}", "callback_data": "noop"})
    if page < pages-1:
        nav.append({"text": "▶️", "callback_data": f"page_{page+1}"})
    keyboard["inline_keyboard"].append(nav)

    actions = []
    if bot_state['selected_brands']:
        actions.append({"text": "Очистить", "callback_data": "clear_all"})
    actions.append({"text": "◀️ Назад", "callback_data": "main_menu"})
    keyboard["inline_keyboard"].append(actions)

    var_count = len(expand_selected_brands()) if bot_state['selected_brands'] else 0
    msg = f"📋 Выбрано: {len(bot_state['selected_brands'])} / вариаций: {var_count}"
    send_telegram_message(msg, keyboard=keyboard)

def send_select_brands_menu(chat_id=None):
    selected = len(bot_state['selected_brands'])
    variations = len(expand_selected_brands()) if selected else 0
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ Популярные (10)", "callback_data": "select_popular"}],
            [{"text": "🎲 Случайные 5", "callback_data": "random_5"}],
            [{"text": "🎲 Случайные 10", "callback_data": "random_10"}],
            [{"text": "📋 Выбрать из списка", "callback_data": "brands_list"}],
            [{"text": "❌ Очистить все", "callback_data": "clear_all"}],
            [{"text": "◀️ Назад", "callback_data": "main_menu"}]
        ]
    }
    msg = f"🔄 Выбрано: {selected} / вариаций: {variations}"
    send_telegram_message(msg, keyboard=keyboard)

# ==================== ОБРАБОТКА КОМАНД ====================
def handle_telegram_update(update):
    try:
        if 'callback_query' in update:
            q = update['callback_query']
            data = q['data']
            chat_id = q['from']['id']
            token = os.environ.get('TELEGRAM_BOT_TOKEN')
            if token:
                requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                              json={'callback_query_id': q['id']})

            if data == 'main_menu':
                send_main_menu(chat_id)
            elif data == 'mode_menu':
                send_mode_menu(chat_id)
            elif data == 'mode_auto':
                with state_lock:
                    bot_state['mode'] = 'auto'
                send_telegram_message("✅ Режим: автоматический")
                send_main_menu(chat_id)
            elif data == 'mode_manual':
                with state_lock:
                    if bot_state['selected_brands']:
                        bot_state['mode'] = 'manual'
                        send_telegram_message(f"✅ Режим: ручной ({len(bot_state['selected_brands'])} брендов)")
                    else:
                        send_telegram_message("⚠️ Сначала выберите бренды!")
                send_main_menu(chat_id)
            elif data == 'start_check':
                if bot_state['is_checking']:
                    send_telegram_message("⚠️ Уже выполняется")
                else:
                    Thread(target=check_all_marketplaces).start()
            elif data == 'stats':
                with state_lock:
                    var_count = len(expand_selected_brands()) if bot_state['selected_brands'] else 0
                    msg = f"""📊 Статистика
Проверок: {bot_state['stats']['total_checks']}
Найдено: {bot_state['stats']['total_finds']}
Режим: {bot_state['mode']}
Статус: {'⏸ ПАУЗА' if bot_state['paused'] else '▶️ АКТИВЕН'}
Выбрано: {len(bot_state['selected_brands'])} / вариаций: {var_count}
Последняя проверка: {bot_state['last_check'] or 'никогда'}
Брендов в базе: {len(BRAND_MAIN_NAMES)}
Всего вариаций: {len(ALL_BRAND_VARIATIONS)}"""
                keyboard = {"inline_keyboard": [[{"text": "◀️ Назад", "callback_data": "main_menu"}]]}
                send_telegram_message(msg, keyboard=keyboard)
            elif data == 'interval':
                kb = {
                    "inline_keyboard": [
                        [{"text": "15 мин", "callback_data": "int_15"},
                         {"text": "30 мин", "callback_data": "int_30"}],
                        [{"text": "1 час", "callback_data": "int_60"},
                         {"text": "3 часа", "callback_data": "int_180"}],
                        [{"text": "6 часов", "callback_data": "int_360"}],
                        [{"text": "12 часов", "callback_data": "int_720"}],
                        [{"text": "◀️ Назад", "callback_data": "main_menu"}]
                    ]
                }
                with state_lock:
                    current = bot_state['interval']
                send_telegram_message(f"⏱ Текущий интервал: {current} мин", keyboard=kb)
            elif data.startswith('int_'):
                new_interval = int(data.split('_')[1])
                with state_lock:
                    bot_state['interval'] = new_interval
                send_telegram_message(f"✅ Интервал установлен: {new_interval} мин")
                send_main_menu(chat_id)
            elif data == 'toggle_pause':
                with state_lock:
                    bot_state['paused'] = not bot_state['paused']
                    status = "⏸ ПАУЗА" if bot_state['paused'] else "▶️ АКТИВЕН"
                send_telegram_message(f"Статус изменён: {status}")
                send_main_menu(chat_id)
            elif data == 'select_brands_menu':
                send_select_brands_menu(chat_id)
            elif data == 'brands_list':
                send_brands_list(0, chat_id)
            elif data.startswith('page_'):
                page = int(data.split('_')[1])
                send_brands_list(page, chat_id)
            elif data.startswith('toggle_'):
                brand = data[7:]
                with state_lock:
                    if brand in bot_state['selected_brands']:
                        bot_state['selected_brands'].remove(brand)
                        cnt = len(get_brand_variations(brand))
                        send_telegram_message(f"❌ {brand} убран")
                    else:
                        bot_state['selected_brands'].append(brand)
                        cnt = len(get_brand_variations(brand))
                        send_telegram_message(f"✅ {brand} добавлен")
                send_brands_list(0, chat_id)
            elif data == 'select_popular':
                with state_lock:
                    bot_state['selected_brands'] = POPULAR_BRANDS.copy()
                    var = len(expand_selected_brands())
                send_telegram_message(f"✅ {len(POPULAR_BRANDS)} популярных брендов")
                send_select_brands_menu(chat_id)
            elif data == 'random_5':
                if len(BRAND_MAIN_NAMES) < 5:
                    send_telegram_message("⚠️ В базе менее 5 брендов")
                else:
                    import random
                    rnd = random.sample(BRAND_MAIN_NAMES, 5)
                    with state_lock:
                        bot_state['selected_brands'] = rnd
                        var = len(expand_selected_brands())
                    send_telegram_message(f"✅ 5 случайных брендов")
                    send_select_brands_menu(chat_id)
            elif data == 'random_10':
                if len(BRAND_MAIN_NAMES) < 10:
                    send_telegram_message("⚠️ В базе менее 10 брендов")
                else:
                    import random
                    rnd = random.sample(BRAND_MAIN_NAMES, 10)
                    with state_lock:
                        bot_state['selected_brands'] = rnd
                        var = len(expand_selected_brands())
                    send_telegram_message(f"✅ 10 случайных брендов")
                    send_select_brands_menu(chat_id)
            elif data == 'clear_all':
                with state_lock:
                    bot_state['selected_brands'] = []
                send_telegram_message("🗑 Список очищен")
                send_select_brands_menu(chat_id)
            elif data == 'noop':
                pass
        elif 'message' in update:
            chat_id = update['message']['chat']['id']
            text = update['message'].get('text', '')
            if text == '/start':
                send_main_menu(chat_id)
            elif text.startswith('/'):
                send_telegram_message("❌ Неизвестная команда")
    except Exception as e:
        logger.error(f"Ошибка в обработчике: {e}")

# ==================== ПАРСИНГ ====================
def safe_select(element, selectors):
    for selector in selectors:
        elem = element.select_one(selector)
        if elem:
            return elem
    return None

def make_request(url, headers=None, timeout=REQUEST_TIMEOUT, retries=MAX_RETRIES):
    if headers is None:
        headers = {'User-Agent': get_next_user_agent()}
    proxies = {'http': PROXY, 'https': PROXY} if PROXY else None

    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout, proxies=proxies)
            r.raise_for_status()
            return r
        except requests.exceptions.Timeout:
            logger.warning(f"Таймаут {attempt+1}/{retries} для {url}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                logger.warning(f"Блокировка 403 для {url} - используем другой User-Agent")
                headers = {'User-Agent': get_next_user_agent()}
            else:
                logger.warning(f"HTTP ошибка {attempt+1}/{retries} для {url}: {e}")
        except Exception as e:
            logger.warning(f"Ошибка {attempt+1}/{retries} для {url}: {e}")

        if attempt < retries - 1:
            time.sleep(RETRY_DELAY * (attempt + 1))

    return None

def parse_ebay(brand):
    items = []
    url = f"https://www.ebay.com/sch/i.html?_nkw={quote(brand)}&_sop=10&_ipg=25"
    resp = make_request(url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, 'lxml')
    cards = soup.select('li.s-item')[:10]

    for card in cards:
        try:
            title_elem = safe_select(card, ['.s-item__title', '.s-item__title span'])
            if not title_elem or 'Shop on' in title_elem.text:
                continue

            price_elem = safe_select(card, ['.s-item__price', '.s-item__price span'])
            link_elem = card.select_one('a.s-item__link')
            if not link_elem:
                continue

            img_elem = card.select_one('.s-item__image-img')
            img_url = None
            if img_elem:
                img_url = img_elem.get('src') or img_elem.get('data-src')

            items.append({
                'title': title_elem.text.strip()[:80],
                'price': price_elem.text.strip()[:30] if price_elem else "Цена не указана",
                'url': link_elem.get('href').split('?')[0],
                'img_url': img_url,
                'source': 'eBay'
            })
        except Exception as e:
            continue

    return items

def parse_mercari(brand):
    items = []
    url = f"https://jp.mercari.com/search?keyword={quote(brand)}&order=desc&sort=created_time"
    resp = make_request(url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, 'lxml')
    cards = soup.select('[data-testid="item-cell"]')[:10]

    for card in cards:
        try:
            title_elem = safe_select(card, ['[data-testid="thumbnail-title"]'])
            price_elem = safe_select(card, ['[data-testid="price"]'])
            link_elem = card.select_one('a')
            if not link_elem:
                continue

            img_elem = card.select_one('img')
            img_url = None
            if img_elem:
                img_url = img_elem.get('src') or img_elem.get('data-src')

            href = link_elem.get('href')
            if href.startswith('http'):
                full_url = href
            else:
                full_url = urljoin('https://jp.mercari.com', href)

            items.append({
                'title': title_elem.text.strip()[:80] if title_elem else "No title",
                'price': price_elem.text.strip()[:30] if price_elem else "Цена не указана",
                'url': full_url,
                'img_url': img_url,
                'source': 'Mercari JP'
            })
        except Exception as e:
            continue

    return items

def parse_2ndstreet(brand):
    items = []
    url = f"https://2ndstreet.jp/en/search?keyword={quote(brand)}&order=6"
    resp = make_request(url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, 'lxml')
    cards = soup.select('.product-list-item')[:10]

    for card in cards:
        try:
            title_elem = safe_select(card, ['.product-name a'])
            price_elem = safe_select(card, ['.product-price'])
            link_elem = card.select_one('a')
            if not link_elem:
                continue

            img_elem = card.select_one('img')
            img_url = None
            if img_elem:
                img_url = img_elem.get('src') or img_elem.get('data-src')

            href = link_elem.get('href')
            if href.startswith('http'):
                full_url = href
            else:
                full_url = urljoin('https://2ndstreet.jp', href)

            items.append({
                'title': title_elem.text.strip()[:80] if title_elem else "No title",
                'price': price_elem.text.strip()[:30] if price_elem else "Цена не указана",
                'url': full_url,
                'img_url': img_url,
                'source': '2nd Street'
            })
        except Exception as e:
            continue

    return items

parsers = {
    'eBay': parse_ebay,
    'Mercari': parse_mercari,
    '2nd Street': parse_2ndstreet,
}

# ==================== ПРОВЕРКА ====================
def check_brands(brands_list):
    found = load_found_items()
    new = 0
    total = len(brands_list)
    start = time.time()

    for idx, brand in enumerate(brands_list, 1):
        with state_lock:
            if bot_state['paused'] or bot_state['shutdown']:
                logger.info("Проверка остановлена")
                break

        time.sleep(random.uniform(5, 10))
        logger.info(f"[{idx}/{total}] Поиск: {brand}")

        for site_name, parser_func in parsers.items():
            with state_lock:
                if bot_state['paused'] or bot_state['shutdown']:
                    break

            time.sleep(random.uniform(3, 6))
            logger.info(f"  {site_name}...")

            try:
                items = parser_func(brand)
                logger.info(f"  найдено {len(items)} товаров")

                for item in items:
                    item_id = generate_item_id(item)
                    if item_id not in found:
                        found[item_id] = item
                        new += 1
                        msg = (f"🆕 <b>{item['title'][:50]}</b>\n"
                               f"💰 {item['price']}\n"
                               f"🏷 {item['source']}\n"
                               f"🔗 <a href='{item['url']}'>Ссылка</a>")
                        send_telegram_message(msg, item.get('img_url'))
                        time.sleep(1)
            except Exception as e:
                logger.error(f"Ошибка парсинга {site_name}: {e}")

    with state_lock:
        bot_state['stats']['total_checks'] += total
        bot_state['stats']['total_finds'] += new
        bot_state['last_check'] = time.strftime('%Y-%m-%d %H:%M:%S')
        bot_state['is_checking'] = False

    if new > 0:
        save_found_items(found)

    elapsed = time.time() - start
    msg = f"✅ Проверка завершена! Найдено: {new}, время: {elapsed:.1f}с"
    send_telegram_message(msg)
    logger.info(msg)

def check_all_marketplaces():
    # Защита от запуска в первые 30 секунд после старта бота
    if time.time() - BOT_START_TIME < 30:
        logger.info("Бот в прогрузке, проверка отложена")
        return

    with state_lock:
        if bot_state['is_checking']:
            send_telegram_message("⚠️ Уже выполняется")
            return

        if bot_state['paused']:
            send_telegram_message("⚠️ Бот на паузе")
            return

        bot_state['is_checking'] = True

        if bot_state['mode'] == 'auto':
            all_vars = ALL_BRAND_VARIATIONS.copy()
            if len(all_vars) > 30:
                import random
                random.shuffle(all_vars)
                brands_to_check = all_vars[:30]
                logger.info(f"Авто: выбрано 30 вариаций из {len(all_vars)}")
            else:
                brands_to_check = all_vars
            send_telegram_message(f"🚀 Авто: {len(brands_to_check)} вариаций")
        else:
            if not bot_state['selected_brands']:
                send_telegram_message("❌ Нет выбранных брендов")
                bot_state['is_checking'] = False
                return
            brands_to_check = expand_selected_brands()
            send_telegram_message(f"🚀 Ручной: {len(brands_to_check)} вариаций")

    Thread(target=check_brands, args=(brands_to_check,)).start()

# ==================== ВЕБХУК ====================
app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'POST':
        Thread(target=handle_telegram_update, args=(request.json,)).start()
        return 'OK', 200
    return home()

@app.route('/')
def home():
    with state_lock:
        status = "⏸ ПАУЗА" if bot_state['paused'] else "▶️ АКТИВЕН"
        uptime = int(time.time() - BOT_START_TIME)
        return f"""
        <h1>Бот активен</h1>
        <p>Режим: {bot_state['mode']}</p>
        <p>Статус: {status}</p>
        <p>Аптайм: {uptime} сек</p>
        <p>Выбрано брендов: {len(bot_state['selected_brands'])}</p>
        <p>Последняя проверка: {bot_state['last_check'] or 'никогда'}</p>
        <p>Найдено товаров: {bot_state['stats']['total_finds']}</p>
        <p>Проверок: {bot_state['stats']['total_checks']}</p>
        """

@app.route('/status')
def status():
    with state_lock:
        return {
            'uptime': int(time.time() - BOT_START_TIME),
            'mode': bot_state['mode'],
            'paused': bot_state['paused'],
            'selected_brands': len(bot_state['selected_brands']),
            'last_check': bot_state['last_check'],
            'total_checks': bot_state['stats']['total_checks'],
            'total_finds': bot_state['stats']['total_finds']
        }

# ==================== ПЛАНИРОВЩИК ====================
def run_scheduler():
    logger.info("Планировщик запущен")
    last_run = 0
    first_check = True

    while not bot_state.get('shutdown', False):
        with state_lock:
            interval = bot_state['interval'] * 60
            paused = bot_state['paused']

        current_time = time.time()

        if not paused and not first_check and (current_time - last_run) >= interval:
            logger.info(f"Планировщик: запуск проверки")
            Thread(target=check_all_marketplaces).start()
            last_run = current_time
        elif first_check:
            first_check = False
            logger.info("Первый запуск — пропускаем автоматическую проверку")
            last_run = current_time

        time.sleep(30)

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    logger.info("🚀 Запуск бота...")

    found = load_found_items()
    logger.info(f"Загружено {len(found)} ранее найденных товаров")

    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if token:
        webhook_url = os.environ.get('WEBHOOK_URL', "https://marketplace-bot.onrender.com")
        try:
            response = requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}")
            if response.status_code == 200:
                logger.info(f"✅ Вебхук установлен: {webhook_url}")
            else:
                logger.error(f"❌ Ошибка установки вебхука: {response.text}")
        except Exception as e:
            logger.error(f"❌ Ошибка вебхука: {e}")

    scheduler_thread = Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    time.sleep(2)

    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Запуск Flask на порту {port}")
    app.run(host='0.0.0.0', port=port)
    