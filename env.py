import os
from dotenv import load_dotenv

# Загружаем переменные из .env (если используем локально)
load_dotenv()

# ================== Telegram ==================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8146716058:AAEUOcF2y0GPl4Le9LOkqtCUERhHzTsCbsc")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "945746201")

# ================== Проект ==================
PORT = int(os.getenv("PORT", 8080))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://uzbek-production.up.railway.app")

# ================== Прокси / Tor ==================
PROXY_URL = os.getenv("PROXY_URL", None)  # Например socks5://127.0.0.1:9050

# ================== Настройки планировщика ==================
DEFAULT_INTERVAL = int(os.getenv("DEFAULT_INTERVAL", 30))  # в минутах
MAX_THREADS = int(os.getenv("MAX_THREADS", 4))

# ================== Логирование ==================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")