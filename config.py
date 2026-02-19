import logging
import time
from threading import Lock
import os
from brands import ALL_PLATFORMS

# ==================== Логирование ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ==================== Блокировки ====================
state_lock = Lock()          # для изменения состояния бота
file_lock = Lock()            # для работы с файлом found_items.json

# ==================== Время старта ====================
BOT_START_TIME = time.time()

# ==================== Состояние бота ====================
BOT_STATE = {
    "mode": "auto",                       # 'auto' или 'manual'
    "turbo_mode": False,                   # турбо-режим (5 мин)
    "selected_brands": [],                 # выбранные бренды
    "selected_platforms": ALL_PLATFORMS.copy(),  # все по умолчанию
    "last_check": None,                    # время последней проверки
    "is_checking": False,                   # идёт ли проверка
    "paused": False,                        # пауза
    "shutdown": False,                       # флаг завершения
    "interval": 30,                          # интервал в минутах
    "stats": {
        "total_checks": 0,
        "total_finds": 0,
        "platform_stats": {platform: {"checks": 0, "finds": 0} for platform in ALL_PLATFORMS}
    },
    "send_to_telegram": None                  # будет установлена из telegram_bot
}

# ==================== Telegram ====================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ==================== Общие настройки ====================
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3
RETRY_DELAY = 3
ITEMS_PER_PAGE = 10
MAX_WORKERS = 4
PROXY = os.environ.get("PROXY_URL", None)
FOUND_ITEMS_FILE = "found_items.json"