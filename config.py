import logging
import time
from threading import Lock
import os
import threading  # добавлено для Event

from brands import ALL_PLATFORMS

# ==================== Логирование ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ==================== Блокировки ====================
state_lock = Lock()
file_lock = Lock()
proxy_lock = Lock()

# ==================== Событие для остановки проверки (НОВОЕ) ====================
stop_event = threading.Event()

# ==================== Время старта ====================
BOT_START_TIME = time.time()

# ==================== Состояние бота ====================
BOT_STATE = {
    "mode": "auto",
    "turbo_mode": False,
    "selected_brands": [],
    "selected_platforms": ALL_PLATFORMS.copy(),
    "last_check": None,
    "is_checking": False,
    "paused": False,
    "shutdown": False,
    "interval": 30,
    "stats": {
        "total_checks": 0,
        "total_finds": 0,
        "platform_stats": {platform: {"checks": 0, "finds": 0} for platform in ALL_PLATFORMS}
    },
    "send_to_telegram": None,
    "awaiting_proxy": False,
    # stop_requested больше не нужен, используем stop_event
}

# ==================== Telegram ====================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ==================== Настройки HTTP-запросов ====================
REQUEST_TIMEOUT = 30
MAX_RETRIES = 5
RETRY_DELAY = 5
ITEMS_PER_PAGE = 10
MAX_WORKERS = 8
PROXY_FILE = "proxies.json"

# ==================== Настройки маскировки ====================
MIN_DELAY_BETWEEN_REQUESTS = 2
MAX_DELAY_BETWEEN_REQUESTS = 5
MIN_DELAY_BETWEEN_BRANDS = 5
MAX_DELAY_BETWEEN_BRANDS = 10
REQUESTS_BEFORE_PROXY_CHANGE = 3

# ==================== Прокси ====================
PROXY_POOL = []
USE_PROXY_POOL = True

# ==================== User-Agent ====================
USER_AGENTS_COUNT = 50

# ==================== Заголовки браузера ====================
BROWSER_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
}