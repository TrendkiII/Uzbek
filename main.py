from flask import Flask, request
from threading import Thread
from config import BOT_STATE, PORT, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, logger
from telegram_bot import handle_telegram_update, send_telegram_message
from scheduler import run_scheduler, check_all_marketplaces

app = Flask(__name__)

# ================== Вебхук ==================
@app.route('/', methods=['POST'])
def webhook():
    """
    Основной вебхук Telegram.
    Любое входящее обновление передаем в обработчик.
    """
    update = request.json
    Thread(target=handle_telegram_update, args=(update,)).start()
    return 'OK', 200

@app.route('/', methods=['GET'])
def home():
    """
    Страница для проверки состояния бота.
    """
    uptime = int(time.time() - BOT_STATE.get("start_time", time.time()))
    total_found = len(BOT_STATE.get("found_items", {}))
    return f"Бот активен. Аптайм: {uptime} сек. Найдено: {total_found}"

# ================== Фоновый планировщик ==================
def start_scheduler():
    """
    Запуск планировщика в отдельном потоке.
    """
    scheduler_thread = Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    logger.info("Планировщик запущен")

# ================== Live-режим ==================
def start_live_mode(chat_id=None):
    """
    Запуск live-режима: поиск выбранных брендов и площадок
    и отправка найденных товаров в Telegram прямо в чат.
    """
    if not chat_id:
        chat_id = TELEGRAM_CHAT_ID
    Thread(target=check_all_marketplaces, kwargs={"live_mode": True}).start()
    send_telegram_message("🚀 Live-поиск запущен", chat_id=chat_id)

# ================== Запуск бота ==================
if __name__ == "__main__":
    import time
    BOT_STATE["start_time"] = time.time()
    BOT_STATE["chat_id"] = TELEGRAM_CHAT_ID

    # Установка вебхука для Telegram
    if TELEGRAM_BOT_TOKEN:
        webhook_url = BOT_STATE.get("webhook_url", "https://ваш-проект.railway.app")
        try:
            import requests
            r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url={webhook_url}")
            if r.status_code == 200:
                logger.info(f"Вебхук установлен: {webhook_url}")
        except Exception as e:
            logger.error(f"Ошибка установки вебхука: {e}")

    # Запуск планировщика
    start_scheduler()

    # Запуск Flask
    app.run(host='0.0.0.0', port=PORT, threaded=True)