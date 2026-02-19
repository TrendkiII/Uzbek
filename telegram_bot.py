import json
import time
import hashlib
from threading import Thread
from flask import Flask, request
import requests

from config import (
    bot_state, state_lock, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    logger, ALL_PLATFORMS, BRAND_MAIN_NAMES, POPULAR_BRANDS
)
from utils import send_telegram_message, send_telegram_album, load_found_items, save_found_items, generate_item_id
from parsers import PARSERS
from brands import get_variations_for_platform, expand_selected_brands_for_platforms

app = Flask(__name__)

# ==================== Функции меню ====================

def send_main_menu(chat_id=None):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🚀 Запустить проверку", "callback_data": "start_check"}],
            [{"text": "⚙️ Режим работы", "callback_data": "mode_menu"}],
            [{"text": "🌐 Выбор площадок", "callback_data": "platforms_menu"}],
            [{"text": "📊 Статистика", "callback_data": "stats"}],
            [{"text": "📋 Список брендов", "callback_data": "brands_list"}],
            [{"text": "⏱ Интервал", "callback_data": "interval"}],
            [{"text": "🔄 Выбрать бренды", "callback_data": "select_brands_menu"}],
            [{"text": "⏸ Пауза / ▶️ Продолжить", "callback_data": "toggle_pause"}]
        ]
    }
    with state_lock:
        platforms = ", ".join(bot_state['selected_platforms']) if bot_state['selected_platforms'] else "Нет"
        brands_info = f"Выбрано: {len(bot_state['selected_brands'])}" if bot_state['selected_brands'] else "Бренды не выбраны"
        pause_status = "⏸ ПАУЗА" if bot_state['paused'] else "▶️ АКТИВЕН"
        msg = (
            f"🤖 Мониторинг\n"
            f"Режим: {bot_state['mode']}\n"
            f"Статус: {pause_status}\n"
            f"Площадки: {platforms}\n"
            f"{brands_info}\n"
            f"Проверок: {bot_state['stats']['total_checks']}\n"
            f"Найдено: {bot_state['stats']['total_finds']}\n"
            f"Последняя: {bot_state['last_check'] or 'никогда'}"
        )
    send_telegram_message(msg, keyboard=keyboard, chat_id=chat_id)

def send_mode_menu(chat_id=None):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🤖 Авто (все вариации)", "callback_data": "mode_auto"}],
            [{"text": "👆 Ручной (выбранные бренды)", "callback_data": "mode_manual"}],
            [{"text": "◀️ Назад", "callback_data": "main_menu"}]
        ]
    }
    send_telegram_message("⚙️ Выберите режим:", keyboard=keyboard, chat_id=chat_id)

def send_platforms_menu(chat_id=None):
    keyboard = {"inline_keyboard": []}
    for p in ALL_PLATFORMS:
        with state_lock:
            mark = "✅ " if p in bot_state['selected_platforms'] else ""
        keyboard["inline_keyboard"].append([{"text": f"{mark}{p}", "callback_data": f"toggle_platform_{p}"}])
    keyboard["inline_keyboard"].append([{"text": "◀️ Назад", "callback_data": "main_menu"}])
    send_telegram_message("🌐 Выберите площадки:", keyboard=keyboard, chat_id=chat_id)

def send_brands_list(page=0, chat_id=None):
    per_page = 8
    start = page * per_page
    end = start + per_page
    total = len(BRAND_MAIN_NAMES)
    pages = (total + per_page - 1) // per_page
    slice_names = BRAND_MAIN_NAMES[start:end]

    keyboard = {"inline_keyboard": []}
    for name in slice_names:
        with state_lock:
            mark = "✅ " if name in bot_state['selected_brands'] else ""
        keyboard["inline_keyboard"].append([{"text": f"{mark}{name}", "callback_data": f"toggle_{name}"}])

    # Навигация
    nav = []
    if page > 0:
        nav.append({"text": "◀️", "callback_data": f"page_{page-1}"})
    nav.append({"text": f"{page+1}/{pages}", "callback_data": "noop"})
    if page < pages-1:
        nav.append({"text": "▶️", "callback_data": f"page_{page+1}"})
    keyboard["inline_keyboard"].append(nav)

    # Кнопки действий
    actions = []
    with state_lock:
        if bot_state['selected_brands']:
            actions.append({"text": "❌ Очистить все", "callback_data": "clear_all"})
    actions.append({"text": "◀️ Назад", "callback_data": "main_menu"})
    keyboard["inline_keyboard"].append(actions)

    var_count = 0
    if bot_state['selected_platforms']:
        with state_lock:
            if bot_state['selected_brands']:
                # Примерная оценка числа вариаций (для первой площадки)
                sample_platform = bot_state['selected_platforms'][0]
                vars_list = []
                for brand in bot_state['selected_brands']:
                    vars_list.extend(get_variations_for_platform(brand, sample_platform))
                var_count = len(set(vars_list))
    msg = f"📋 Выбрано: {len(bot_state['selected_brands'])} / вариаций: {var_count} (для первой площадки)"
    send_telegram_message(msg, keyboard=keyboard, chat_id=chat_id)

def send_select_brands_menu(chat_id=None):
    with state_lock:
        selected = len(bot_state['selected_brands'])
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ Популярные (10)", "callback_data": "select_popular"}],
            [{"text": "🎲 Случайные 5", "callback_data": "random_5"}],
            [{"text": "🎲 Случайные 10", "callback_data": "random_10"}],
            [{"text": "📋 Выбрать из списка", "callback_data": "brands_list"}],
            [{"text": "❌ Очистить все", "callback_data": "clear_all"}],
            [{"text": "◀️ Назад", "callback_data": "main_menu"}]
        ]
    }
    msg = f"🔄 Выбрано: {selected}"
    send_telegram_message(msg, keyboard=keyboard, chat_id=chat_id)

def send_stats(chat_id=None):
    with state_lock:
        platform_stats = "\n".join([f"  {p}: {bot_state['stats']['platform_stats'][p]['finds']} находок" for p in ALL_PLATFORMS])
        var_count = 0
        if bot_state['selected_platforms'] and bot_state['selected_brands']:
            sample_platform = bot_state['selected_platforms'][0]
            vars_list = []
            for brand in bot_state['selected_brands']:
                vars_list.extend(get_variations_for_platform(brand, sample_platform))
            var_count = len(set(vars_list))
        msg = (
            f"📊 Статистика\n\n"
            f"Проверок всего: {bot_state['stats']['total_checks']}\n"
            f"Найдено всего: {bot_state['stats']['total_finds']}\n\n"
            f"По площадкам:\n{platform_stats}\n\n"
            f"Режим: {bot_state['mode']}\n"
            f"Статус: {'⏸ ПАУЗА' if bot_state['paused'] else '▶️ АКТИВЕН'}\n"
            f"Выбрано брендов: {len(bot_state['selected_brands'])} / вариаций: {var_count}\n"
            f"Площадок: {len(bot_state['selected_platforms'])}/{len(ALL_PLATFORMS)}\n\n"
            f"Последняя проверка: {bot_state['last_check'] or 'никогда'}"
        )
    keyboard = {"inline_keyboard": [[{"text": "◀️ Назад", "callback_data": "main_menu"}]]}
    send_telegram_message(msg, keyboard=keyboard, chat_id=chat_id)

def send_interval_menu(chat_id=None):
    with state_lock:
        current = bot_state['interval']
    keyboard = {
        "inline_keyboard": [
            [{"text": "15 мин", "callback_data": "int_15"}, {"text": "30 мин", "callback_data": "int_30"}],
            [{"text": "1 час", "callback_data": "int_60"}, {"text": "3 часа", "callback_data": "int_180"}],
            [{"text": "6 часов", "callback_data": "int_360"}],
            [{"text": "12 часов", "callback_data": "int_720"}],
            [{"text": "◀️ Назад", "callback_data": "main_menu"}]
        ]
    }
    send_telegram_message(f"⏱ Текущий интервал: {current} мин", keyboard=keyboard, chat_id=chat_id)

# ==================== Обработчик вебхуков ====================

@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'POST':
        # Запускаем обработку в отдельном потоке, чтобы не блокировать ответ
        Thread(target=handle_update, args=(request.json,)).start()
        return 'OK', 200
    return home()

@app.route('/')
def home():
    with state_lock:
        return f"Бот активен. Найдено: {bot_state['stats']['total_finds']}"

def handle_update(update):
    """Обрабатывает входящее обновление от Telegram."""
    try:
        if 'callback_query' in update:
            q = update['callback_query']
            data = q['data']
            chat_id = q['from']['id']
            token = TELEGRAM_BOT_TOKEN
            # Отвечаем на callback, чтобы убрать часики
            if token:
                requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                              json={'callback_query_id': q['id']})

            # Обработка различных callback_data
            if data == 'main_menu':
                send_main_menu(chat_id)
            elif data == 'mode_menu':
                send_mode_menu(chat_id)
            elif data == 'platforms_menu':
                send_platforms_menu(chat_id)
            elif data == 'stats':
                send_stats(chat_id)
            elif data == 'brands_list':
                send_brands_list(0, chat_id)
            elif data == 'select_brands_menu':
                send_select_brands_menu(chat_id)
            elif data == 'interval':
                send_interval_menu(chat_id)
            elif data == 'toggle_pause':
                with state_lock:
                    bot_state['paused'] = not bot_state['paused']
                    status = "⏸ ПАУЗА" if bot_state['paused'] else "▶️ АКТИВЕН"
                send_telegram_message(f"Статус изменён: {status}", chat_id=chat_id)
                send_main_menu(chat_id)
            elif data == 'mode_auto':
                with state_lock:
                    bot_state['mode'] = 'auto'
                send_telegram_message("✅ Режим: автоматический", chat_id=chat_id)
                send_main_menu(chat_id)
            elif data == 'mode_manual':
                with state_lock:
                    if bot_state['selected_brands']:
                        bot_state['mode'] = 'manual'
                        send_telegram_message(f"✅ Режим: ручной ({len(bot_state['selected_brands'])} брендов)", chat_id=chat_id)
                    else:
                        send_telegram_message("⚠️ Сначала выберите бренды!", chat_id=chat_id)
                send_main_menu(chat_id)
            elif data.startswith('toggle_platform_'):
                platform = data.replace('toggle_platform_', '')
                with state_lock:
                    if platform in bot_state['selected_platforms']:
                        bot_state['selected_platforms'].remove(platform)
                    else:
                        bot_state['selected_platforms'].append(platform)
                send_platforms_menu(chat_id)
            elif data.startswith('page_'):
                page = int(data.split('_')[1])
                send_brands_list(page, chat_id)
            elif data.startswith('toggle_'):
                brand = data[7:]
                with state_lock:
                    if brand in bot_state['selected_brands']:
                        bot_state['selected_brands'].remove(brand)
                        send_telegram_message(f"❌ {brand} убран", chat_id=chat_id)
                    else:
                        bot_state['selected_brands'].append(brand)
                        send_telegram_message(f"✅ {brand} добавлен", chat_id=chat_id)
                send_brands_list(0, chat_id)
            elif data == 'select_popular':
                with state_lock:
                    bot_state['selected_brands'] = POPULAR_BRANDS.copy()
                send_telegram_message(f"✅ {len(POPULAR_BRANDS)} популярных брендов", chat_id=chat_id)
                send_select_brands_menu(chat_id)
            elif data == 'random_5':
                import random
                if len(BRAND_MAIN_NAMES) >= 5:
                    rnd = random.sample(BRAND_MAIN_NAMES, 5)
                    with state_lock:
                        bot_state['selected_brands'] = rnd
                    send_telegram_message("✅ 5 случайных брендов", chat_id=chat_id)
                    send_select_brands_menu(chat_id)
                else:
                    send_telegram_message("⚠️ В базе менее 5 брендов", chat_id=chat_id)
            elif data == 'random_10':
                import random
                if len(BRAND_MAIN_NAMES) >= 10:
                    rnd = random.sample(BRAND_MAIN_NAMES, 10)
                    with state_lock:
                        bot_state['selected_brands'] = rnd
                    send_telegram_message("✅ 10 случайных брендов", chat_id=chat_id)
                    send_select_brands_menu(chat_id)
                else:
                    send_telegram_message("⚠️ В базе менее 10 брендов", chat_id=chat_id)
            elif data == 'clear_all':
                with state_lock:
                    bot_state['selected_brands'] = []
                send_telegram_message("🗑 Список очищен", chat_id=chat_id)
                send_select_brands_menu(chat_id)
            elif data.startswith('int_'):
                new_interval = int(data.split('_')[1])
                with state_lock:
                    bot_state['interval'] = new_interval
                send_telegram_message(f"✅ Интервал установлен: {new_interval} мин", chat_id=chat_id)
                send_main_menu(chat_id)
            elif data == 'start_check':
                if bot_state['is_checking']:
                    send_telegram_message("⚠️ Уже выполняется", chat_id=chat_id)
                else:
                    # Импортируем функцию проверки здесь, чтобы избежать циклических импортов
                    from scheduler import run_check_once
                    Thread(target=run_check_once).start()
        elif 'message' in update:
            chat_id = update['message']['chat']['id']
            text = update['message'].get('text', '')
            if text == '/start':
                send_main_menu(chat_id)
            else:
                send_telegram_message("❌ Неизвестная команда. Используйте /start", chat_id=chat_id)
    except Exception as e:
        logger.error(f"Ошибка в обработчике: {e}")

# Функция для запуска проверки извне (будет вызываться из scheduler)
def run_check_once():
    from scheduler import check_all_marketplaces
    check_all_marketplaces()