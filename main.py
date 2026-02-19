# main.py
import os
import logging
from flask import Flask
from threading import Thread
from scheduler import run_scheduler
from telegram_bot import handle_telegram_update, send_telegram_message
from config import BOT_STATE

# ==================== Логирование ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ==================== Flask ====================
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    with BOT_STATE['state_lock']:
        uptime = int(os.time() - BOT_STATE['BOT_START_TIME'])
        finds = BOT_STATE['stats']['total_finds']
    return f"Бот активен. Аптайм: {uptime} сек. Найдено: {finds}"

@app.route("/", methods=["POST"])
def webhook():
    data = None
    try:
        data = request.json
    except Exception as e:
        logger.error(f"Ошибка получения JSON: {e}")
        return "Bad Request", 400

    if data:
        # Обработка обновления в отдельном потоке
        Thread(target=handle_telegram_update, args=(data,)).start()
    return "OK", 200

# ==================== Фоновый Scheduler ====================
scheduler_thread = Thread(target=run_scheduler)
scheduler_thread.daemon = True
scheduler_thread.start()

# ==================== Запуск Flask ====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Запуск Flask на 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)