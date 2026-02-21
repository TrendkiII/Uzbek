import os
import time
import atexit
from threading import Thread

from config import BOT_STATE, logger, TELEGRAM_BOT_TOKEN
from telegram_bot import app as main_app
from scheduler import run_scheduler
from utils import init_proxy_pool
from database import init_db
from playwright_manager import init_browser, close_browser
from async_loop import start_background_loop, run_coro

# ==================== Запуск планировщика ====================
def start_scheduler():
    scheduler_thread = Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    logger.info("✅ Scheduler запущен в фоне")

# ==================== Установка вебхука ====================
def setup_webhook():
    token = TELEGRAM_BOT_TOKEN
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен!")
        return

    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        railway_url = os.environ.get("RAILWAY_STATIC_URL")
        if railway_url:
            webhook_url = f"https://{railway_url}"
        else:
            webhook_url = os.environ.get("DEFAULT_WEBHOOK_URL", "https://uzbek-production.up.railway.app")
            logger.warning(f"⚠️ WEBHOOK_URL не задан, использую {webhook_url}")

    try:
        import requests
        r = requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}")
        if r.status_code == 200:
            result = r.json()
            if result.get("ok"):
                logger.info(f"✅ Вебхук установлен: {webhook_url}")
            else:
                logger.error(f"❌ Ошибка установки вебхука: {result}")
        else:
            logger.error(f"❌ HTTP ошибка при установке вебхука: {r.status_code}")
    except Exception as e:
        logger.error(f"❌ Ошибка при установке вебхука: {e}")

# ==================== Инициализация Playwright через общий цикл ====================
def init_playwright_async():
    try:
        # Ждём завершения инициализации браузера
        run_coro(init_browser()).result(timeout=30)
    except Exception as e:
        logger.error(f"❌ Failed to initialize Playwright browser: {e}")

def close_playwright_async():
    try:
        run_coro(close_browser()).result(timeout=10)
    except Exception as e:
        logger.error(f"❌ Error closing Playwright: {e}")

# ==================== Основной запуск ====================
if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК БОТА")
    logger.info("=" * 50)

    # Инициализация базы данных SQLite
    try:
        init_db()
        logger.info("✅ База данных SQLite инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")

    # Инициализация прокси из файла
    try:
        init_proxy_pool()
        logger.info("✅ Прокси пул инициализирован")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации прокси: {e}")

    # Запускаем фоновый event loop
    start_background_loop()

    # Инициализируем Playwright браузер в этом цикле
    init_playwright_async()
    atexit.register(close_playwright_async)

    # Установка времени старта
    try:
        BOT_STATE['start_time'] = time.time()
    except Exception as e:
        logger.error(f"❌ Ошибка установки времени старта: {e}")

    # Установка вебхука для основного бота
    setup_webhook()

    # Запуск планировщика
    start_scheduler()

    # Получаем порт из окружения
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")

    logger.info(f"🌍 Основной бот будет доступен на {host}:{port}")
    logger.info(f"🌍 Healthcheck доступен по /health")
    logger.info("=" * 50)

    time.sleep(2)

    # Запуск основного Flask приложения
    try:
        logger.info(f"🚀 Запуск Flask на {host}:{port}")
        main_app.run(host=host, port=port, threaded=True)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске основного бота: {e}")
        time.sleep(5)
        raise