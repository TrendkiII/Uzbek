import logging
from threading import Lock
import os

# ЛОГГЕР - ДОЛЖЕН БЫТЬ ЗДЕСЬ
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

state_lock = Lock()

# КЛАСС CONFIG
class Config:
    BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
    CLAUDE_ENABLED = True
    CLAUDE_API_URL = os.environ.get("CLAUDE_API_URL", "http://localhost:3032")
    REQUEST_TIMEOUT = 30
    ITEMS_PER_PAGE = 10
    PLATFORMS = {
        "mercari": {"name": "Mercari JP", "url": "https://jp.mercari.com", "use_claude": True},
    }

# ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ
BOT_STATE = {
    "selected_brands": [],
    "selected_platforms": ['Mercari JP'],
    "last_check": None,
    "stats": {"total_finds": 0},
}

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
CLAUDE_ENABLED = True
CLAUDE_API_URL = os.environ.get("CLAUDE_API_URL", "http://localhost:3032")
REQUEST_TIMEOUT = 30
ITEMS_PER_PAGE = 10