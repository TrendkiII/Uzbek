import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PORT = int(os.getenv("PORT", 8080))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PROXY_URL = os.getenv("PROXY_URL")
DEFAULT_INTERVAL = int(os.getenv("DEFAULT_INTERVAL", 30))
MAX_THREADS = int(os.getenv("MAX_THREADS", 4))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")