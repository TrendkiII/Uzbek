import os
import time
from fake_useragent import UserAgent

# ================== Telegram ==================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ================== Парсинг ==================
REQUEST_TIMEOUT = 20          # Таймаут для HTTP запросов (сек)
MAX_RETRIES = 3               # Кол-во повторных попыток
RETRY_DELAY = 3               # Задержка между попытками (сек)
ITEMS_PER_PAGE = 10           # Сколько элементов парсить с каждой страницы
PARALLEL_THREADS = 4          # Кол-во потоков для фонового поиска
LIVE_MODE_INTERVAL = 10       # Интервал между проверками в лайв режиме (сек)

# ================== Прокси и User-Agent ==================
PROXY = os.environ.get("PROXY_URL", None)
ua = UserAgent()
USER_AGENTS_POOL = [ua.random for _ in range(20)]
UA_INDEX = 0

def get_next_user_agent():
    global UA_INDEX
    ua = USER_AGENTS_POOL[UA_INDEX % len(USER_AGENTS_POOL)]
    UA_INDEX += 1
    return ua

# ================== Пауза и состояния ==================
BOT_STATE = {
    "active": False,                 # Если True — фоновые проверки идут
    "selected_brands": [],           # Выбранные бренды для поиска
    "selected_platforms": [],        # Выбранные площадки
    "last_items": [],                # Последние найденные элементы (для лайв режима)
    "last_check": None               # Время последней проверки
}

# ================== Логи ==================
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ================== URL шаблоны для поиска ==================
SEARCH_URLS = {
    'Mercari JP': 'https://jp.mercari.com/search?keyword={keyword}',
    'Rakuten Rakuma': 'https://fril.jp/s?query={keyword}',
    'Yahoo Flea': 'https://paypayfleamarket.yahoo.co.jp/search/{keyword}',
    'Yahoo Auction': 'https://auctions.yahoo.co.jp/search/search?p={keyword}&aq=-1&auccat=&ei=utf-8&oq=&sc_i=&tab_ex=commerce&type=all',
    'Yahoo Shopping': 'https://shopping.yahoo.co.jp/search?p={keyword}&ss_first=1&tab_ex=commerce&used=1',
    'Rakuten Mall': 'https://search.rakuten.co.jp/search/mall/{keyword}/?used=1',
    'eBay': 'https://www.ebay.com/sch/i.html?_nkw={keyword}&LH_ItemCondition=4&_sacat=11450',
    '2nd Street JP': 'https://www.2ndstreet.jp/search?query={keyword}'
}

# ================== Общие настройки ==================
MAX_BATCH_SEND = 10       # Сколько элементов в одном пакете для Telegram альбома