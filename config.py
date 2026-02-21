import logging
from threading import Lock
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

state_lock = Lock()

BOT_STATE = {
    "selected_brands": [],
    "selected_platforms": ['Mercari JP'],  # только одну площадку для начала
    "last_check": None,
    "stats": {"total_finds": 0},
}

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

REQUEST_TIMEOUT = 30
ITEMS_PER_PAGE = 10