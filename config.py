"""
config.py - Конфигурация бота
"""

import os
import logging
from threading import Lock

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Блокировка для состояния
state_lock = Lock()

class Config:
    """Класс конфигурации"""
    
    # Токен бота - поддерживает оба имени переменных!
    BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    
    # Отладка токена
    if BOT_TOKEN:
        logger.info(f"✅ Токен бота загружен: {BOT_TOKEN[:10]}...")
    else:
        logger.error("❌ ТОКЕН БОТА НЕ НАЙДЕН!")
        logger.error("Добавь BOT_TOKEN или TELEGRAM_BOT_TOKEN в переменные окружения!")
    
    # ID чата для уведомлений
    CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
    
    # Настройки Claude
    CLAUDE_ENABLED = os.environ.get("CLAUDE_ENABLED", "true").lower() == "true"
    CLAUDE_API_URL = os.environ.get("CLAUDE_API_URL", "http://localhost:3032")
    
    # Настройки парсинга
    REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", 30))
    ITEMS_PER_PAGE = int(os.environ.get("ITEMS_PER_PAGE", 10))
    
    # Доступные платформы
    PLATFORMS = {
        "mercari": {
            "name": "Mercari JP", 
            "url": "https://jp.mercari.com", 
            "use_claude": True
        },
        "ebay": {
            "name": "eBay", 
            "url": "https://www.ebay.com", 
            "use_claude": True
        },
        "vinted": {
            "name": "Vinted", 
            "url": "https://www.vinted.pl", 
            "use_claude": True
        },
        "olx": {
            "name": "OLX", 
            "url": "https://www.olx.pl", 
            "use_claude": True
        },
    }

# Для обратной совместимости - все переменные доступны и так
BOT_STATE = {
    "selected_brands": [],
    "selected_platforms": ['Mercari JP'],
    "last_check": None,
    "stats": {"total_finds": 0},
}

# Экспортируем для удобства
TELEGRAM_BOT_TOKEN = Config.BOT_TOKEN
TELEGRAM_CHAT_ID = Config.CHAT_ID
CLAUDE_ENABLED = Config.CLAUDE_ENABLED
CLAUDE_API_URL = Config.CLAUDE_API_URL
REQUEST_TIMEOUT = Config.REQUEST_TIMEOUT
ITEMS_PER_PAGE = Config.ITEMS_PER_PAGE