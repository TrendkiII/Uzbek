import json
import time
from threading import Thread
import requests
from flask import Flask, request

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, logger, BOT_STATE, state_lock
from database import add_item_with_brand, init_db
from brands import detect_brand_from_title
from simple_parsers import search_all

app = Flask(__name__)

# Простейшее меню
def send_message(text, chat_id=None):
    token = TELEGRAM_BOT_TOKEN
    chat_id = chat_id or TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {'chat_id': chat_id, 'text': text}
    try:
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")

def build_menu():
    return (
        "🔍 Меню\n"
        "1. Запустить поиск\n"
        "2. Статистика\n"
        "3. Помощь"
    )

def handle_message(update):
    chat_id = update['message']['chat']['id']
    text = update['message'].get('text', '')
    
    if text == '/start':
        send_message(build_menu(), chat_id)
    elif text == '1':
        send_message("🔄 Запускаю поиск...", chat_id)
        Thread(target=run_search_thread, args=(chat_id,)).start()
    elif text == '2':
        with state_lock:
            finds = BOT_STATE['stats']['total_finds']
        send_message(f"📊 Найдено товаров: {finds}", chat_id)
    else:
        send_message("Используй /start для меню", chat_id)

def run_search_thread(chat_id):
    keywords = ["LEVIS", "GUCCI", "PRADA"]  # тестовые ключи
    items = search_all(keywords)
    
    new_count = 0
    for item in items:
        brand = detect_brand_from_title(item['title'])
        if add_item_with_brand(item, brand):
            new_count += 1
            with state_lock:
                BOT_STATE['stats']['total_finds'] += 1
    
    send_message(f"✅ Поиск завершен. Новых товаров: {new_count}", chat_id)

@app.route('/', methods=['POST'])
def webhook():
    Thread(target=handle_message, args=(request.json,)).start()
    return 'OK', 200

@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080)