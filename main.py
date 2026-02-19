import os
import time
from threading import Thread
from config import BOT_STATE, logger, BOT_START_TIME, TELEGRAM_BOT_TOKEN
from telegram_bot import app as main_app
from scheduler import run_scheduler
from utils import init_proxy_pool

# ==================== Запуск планировщика ====================
def start_scheduler():
    scheduler_thread = Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    logger.info("✅ Scheduler запущен в фоне")

# ==================== Запуск бота-деплойера ====================
def start_deploy_bot():
    """Запускает бота-деплойера в отдельном потоке"""
    try:
        # Проверяем, есть ли токен для деплойера
        if not os.environ.get("DEPLOY_BOT_TOKEN"):
            logger.warning("⚠️ DEPLOY_BOT_TOKEN не установлен, бот-деплойер не запущен")
            return
            
        # Импортируем здесь, чтобы избежать циклических импортов
        from deploy_bot import run_deploy_bot
        
        deploy_thread = Thread(target=run_deploy_bot)
        deploy_thread.daemon = True
        deploy_thread.start()
        logger.info("✅ Deploy bot запущен в фоне")
    except Exception as e:
        logger.error(f"❌ Не удалось запустить деплойер: {e}")

# ==================== Установка вебхука ====================
def setup_webhook():
    token = TELEGRAM_BOT_TOKEN
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN не установлен!")
        return
        
    # Получаем URL для вебхука из переменных окружения
    webhook_url = os.environ.get("WEBHOOK_URL")
    if not webhook_url:
        # Если не задан, пытаемся определить автоматически
        railway_url = os.environ.get("RAILWAY_STATIC_URL")
        if railway_url:
            webhook_url = f"https://{railway_url}"
        else:
            # fallback для локальной разработки
            webhook_url = "https://your-app.railway.app"
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

# ==================== Основной запуск ====================
if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК БОТА")
    logger.info("=" * 50)
    
    # Инициализация прокси из файла
    init_proxy_pool()
    
    # Установка времени старта
    with main_app.config.get('state_lock', BOT_STATE.get('state_lock')):
        BOT_STATE['start_time'] = time.time()
    
    # Установка вебхука для основного бота
    setup_webhook()
    
    # Запуск планировщика (основной бот)
    start_scheduler()
    
    # Запуск бота-деплойера (отдельный поток)
    start_deploy_bot()
    
    # Получаем порт из окружения
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")
    
    logger.info(f"🌍 Основной бот будет доступен на {host}:{port}")
    logger.info(f"🌍 Healthcheck доступен по /health")
    logger.info("=" * 50)
    
    # Запуск основного Flask приложения
    try:
        main_app.run(host=host, port=port, threaded=True)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске основного бота: {e}")
        # Даём время на отправку сообщения об ошибке
        time.sleep(5)
        raise