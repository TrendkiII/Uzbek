import os
import time
from threading import Thread
from config import BOT_STATE, logger, BOT_START_TIME, TELEGRAM_BOT_TOKEN
from telegram_bot import app as main_app
from scheduler import run_scheduler
from utils import init_proxy_pool

def start_scheduler():
    scheduler_thread = Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    logger.info("✅ Scheduler запущен в фоне")

def start_deploy_bot():
    try:
        if not os.environ.get("DEPLOY_BOT_TOKEN"):
            logger.warning("⚠️ DEPLOY_BOT_TOKEN не установлен, бот-деплойер не запущен")
            return
        from deploy_bot import run_deploy_bot
        deploy_thread = Thread(target=run_deploy_bot, daemon=True)
        deploy_thread.start()
        logger.info("✅ Deploy bot запущен в фоне")
        time.sleep(2)
        if deploy_thread.is_alive():
            logger.info("✅ Deploy bot работает")
        else:
            logger.error("❌ Deploy bot умер сразу после запуска")
    except Exception as e:
        logger.error(f"❌ Не удалось запустить деплойер: {e}")

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
            webhook_url = "https://your-app.railway.app"
            logger.warning(f"⚠️ WEBHOOK_URL не задан, использую {webhook_url}")
    try:
        import requests
        r = requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}")
        if r.status_code == 200 and r.json().get("ok"):
            logger.info(f"✅ Вебхук установлен: {webhook_url}")
        else:
            logger.error(f"❌ Ошибка установки вебхука: {r.text}")
    except Exception as e:
        logger.error(f"❌ Ошибка при установке вебхука: {e}")

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("🚀 ЗАПУСК БОТА")
    logger.info("=" * 50)

    init_proxy_pool()
    setup_webhook()
    start_scheduler()
    start_deploy_bot()

    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")
    logger.info(f"🌍 Основной бот будет доступен на {host}:{port}")
    logger.info(f"🌍 Healthcheck доступен по /health")
    logger.info("=" * 50)

    try:
        main_app.run(host=host, port=port, threaded=True)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске основного бота: {e}")
        time.sleep(5)
        raise