import os
import time
from threading import Thread
from config import BOT_STATE, logger, BOT_START_TIME, TELEGRAM_BOT_TOKEN
from telegram_bot import app
from scheduler import run_scheduler

def start_scheduler():
    scheduler_thread = Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    logger.info("✅ Scheduler запущен в фоне")

if __name__ == "__main__":
    # Устанавливаем вебхук
    token = TELEGRAM_BOT_TOKEN
    if token:
        webhook_url = os.environ.get("WEBHOOK_URL", "https://your-app.railway.app")
        try:
            import requests
            r = requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}")
            if r.status_code == 200:
                logger.info(f"✅ Вебхук установлен: {webhook_url}")
        except Exception as e:
            logger.error(f"❌ Ошибка установки вебхука: {e}")

    # Запуск планировщика
    start_scheduler()

    # Запуск Flask
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск Flask на 0.0.0.0:{port}")
    logger.info(f"🌍 Healthcheck доступен по /health")
    app.run(host="0.0.0.0", port=port, threaded=True)