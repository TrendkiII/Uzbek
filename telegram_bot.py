import json
import time
import requests
from threading import Thread
from flask import Flask, request

from config import (
    BOT_STATE, state_lock, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    logger, ALL_PLATFORMS, PROXY_POOL
)
from brands import BRAND_MAIN_NAMES, POPULAR_BRANDS, get_variations_for_platform
from parsers import PARSERS
from utils import (
    generate_item_id, test_proxy, add_proxy_to_pool, 
    check_and_update_proxies, get_proxy_stats
)

app = Flask(__name__)

# ==================== Функции отправки ====================
def send_telegram_message(text, photo_url=None, keyboard=None, chat_id=None):
    token = TELEGRAM_BOT_TOKEN
    if not token:
        logger.error("Нет TELEGRAM_BOT_TOKEN")
        return False
    if not chat_id:
        chat_id = TELEGRAM_CHAT_ID
        if not chat_id:
            logger.error("Нет chat_id")
            return False
    try:
        if photo_url:
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            payload = {
                'chat_id': chat_id,
                'photo': photo_url,
                'caption': text,
                'parse_mode': 'HTML'
            }
            if keyboard:
                payload['reply_markup'] = json.dumps(keyboard)
            requests.post(url, data=payload, timeout=10)
        else:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            }
            if keyboard:
                payload['reply_markup'] = json.dumps(keyboard)
            requests.post(url, data=payload, timeout=10)
        return True
    except Exception as e:
        logger.error(f"Ошибка Telegram: {e}")
        return False

def send_telegram_album(media_group, chat_id=None):
    token = TELEGRAM_BOT_TOKEN
    if not token:
        return False
    if not chat_id:
        chat_id = TELEGRAM_CHAT_ID
        if not chat_id:
            logger.error("Нет chat_id")
            return False
    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
    payload = {
        'chat_id': chat_id,
        'media': json.dumps(media_group)
    }
    try:
        requests.post(url, data=payload, timeout=15)
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки альбома: {e}")
        return False

# ==================== Функции меню ====================

def send_main_menu(chat_id=None):
    turbo_status = "🐱‍🏍 ТУРБО" if BOT_STATE.get('turbo_mode') else "🐢 Обычный"
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "🚀 Запустить проверку", "callback_data": "start_check"}],
            [{"text": "⚙️ Режим работы", "callback_data": "mode_menu"}],
            [{"text": f"⚡ Режим: {turbo_status}", "callback_data": "toggle_turbo"}],
            [{"text": "🌐 Выбор площадок", "callback_data": "platforms_menu"}],
            [{"text": "📊 Статистика", "callback_data": "stats"}],
            [{"text": "📋 Список брендов", "callback_data": "brands_list"}],
            [{"text": "⏱ Интервал", "callback_data": "interval"}],
            [{"text": "🔄 Выбрать бренды", "callback_data": "select_brands_menu"}],
            [{"text": "🔧 Управление прокси", "callback_data": "proxy_menu"}],
            [{"text": "⏸ Пауза / ▶️ Продолжить", "callback_data": "toggle_pause"}]
        ]
    }
    with state_lock:
        platforms = ", ".join(BOT_STATE['selected_platforms']) if BOT_STATE['selected_platforms'] else "Нет"
        brands_info = f"Выбрано: {len(BOT_STATE['selected_brands'])}" if BOT_STATE['selected_brands'] else "Бренды не выбраны"
        pause_status = "⏸ ПАУЗА" if BOT_STATE['paused'] else "▶️ АКТИВЕН"
        msg = (
            f"🤖 Мониторинг\n"
            f"Режим: {BOT_STATE['mode']}\n"
            f"Турбо: {'Вкл' if BOT_STATE.get('turbo_mode') else 'Выкл'}\n"
            f"Статус: {pause_status}\n"
            f"Площадки: {platforms}\n"
            f"{brands_info}\n"
            f"Прокси в пуле: {len(PROXY_POOL)}\n"
            f"Проверок: {BOT_STATE['stats']['total_checks']}\n"
            f"Найдено: {BOT_STATE['stats']['total_finds']}\n"
            f"Последняя: {BOT_STATE['last_check'] or 'никогда'}"
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
            mark = "✅ " if p in BOT_STATE['selected_platforms'] else ""
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
            mark = "✅ " if name in BOT_STATE['selected_brands'] else ""
        keyboard["inline_keyboard"].append([{"text": f"{mark}{name}", "callback_data": f"toggle_{name}"}])

    nav = []
    if page > 0:
        nav.append({"text": "◀️", "callback_data": f"page_{page-1}"})
    nav.append({"text": f"{page+1}/{pages}", "callback_data": "noop"})
    if page < pages-1:
        nav.append({"text": "▶️", "callback_data": f"page_{page+1}"})
    keyboard["inline_keyboard"].append(nav)

    actions = []
    with state_lock:
        if BOT_STATE['selected_brands']:
            actions.append({"text": "❌ Очистить все", "callback_data": "clear_all"})
    actions.append({"text": "◀️ Назад", "callback_data": "main_menu"})
    keyboard["inline_keyboard"].append(actions)

    # Подсчёт вариаций для первой платформы
    var_count = 0
    if BOT_STATE['selected_platforms']:
        with state_lock:
            if BOT_STATE['selected_brands']:
                sample_platform = BOT_STATE['selected_platforms'][0]
                vars_list = []
                for brand in BOT_STATE['selected_brands']:
                    vars_list.extend(get_variations_for_platform(brand, sample_platform))
                var_count = len(set(vars_list))
    msg = f"📋 Выбрано: {len(BOT_STATE['selected_brands'])} / вариаций: {var_count} (для первой площадки)"
    send_telegram_message(msg, keyboard=keyboard, chat_id=chat_id)

def send_select_brands_menu(chat_id=None):
    with state_lock:
        selected = len(BOT_STATE['selected_brands'])
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
        platform_stats = "\n".join([f"  {p}: {BOT_STATE['stats']['platform_stats'][p]['finds']} находок" for p in ALL_PLATFORMS])
        var_count = 0
        if BOT_STATE['selected_platforms'] and BOT_STATE['selected_brands']:
            sample_platform = BOT_STATE['selected_platforms'][0]
            vars_list = []
            for brand in BOT_STATE['selected_brands']:
                vars_list.extend(get_variations_for_platform(brand, sample_platform))
            var_count = len(set(vars_list))
        msg = (
            f"📊 Статистика\n\n"
            f"Проверок всего: {BOT_STATE['stats']['total_checks']}\n"
            f"Найдено всего: {BOT_STATE['stats']['total_finds']}\n\n"
            f"По площадкам:\n{platform_stats}\n\n"
            f"Режим: {BOT_STATE['mode']}\n"
            f"Турбо: {'Вкл' if BOT_STATE.get('turbo_mode') else 'Выкл'}\n"
            f"Статус: {'⏸ ПАУЗА' if BOT_STATE['paused'] else '▶️ АКТИВЕН'}\n"
            f"Выбрано брендов: {len(BOT_STATE['selected_brands'])} / вариаций: {var_count}\n"
            f"Площадок: {len(BOT_STATE['selected_platforms'])}/{len(ALL_PLATFORMS)}\n"
            f"Прокси в пуле: {len(PROXY_POOL)}\n\n"
            f"Последняя проверка: {BOT_STATE['last_check'] or 'никогда'}"
        )
    keyboard = {"inline_keyboard": [[{"text": "◀️ Назад", "callback_data": "main_menu"}]]}
    send_telegram_message(msg, keyboard=keyboard, chat_id=chat_id)

def send_interval_menu(chat_id=None):
    with state_lock:
        current = BOT_STATE['interval']
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

# ==================== Меню управления прокси ====================
def send_proxy_menu(chat_id=None):
    with state_lock:
        proxy_count = len(PROXY_POOL)
    keyboard = {
        "inline_keyboard": [
            [{"text": "➕ Добавить прокси", "callback_data": "proxy_add"}],
            [{"text": "🔍 Проверить все", "callback_data": "proxy_check"}],
            [{"text": "📊 Статистика", "callback_data": "proxy_stats"}],
            [{"text": "🗑 Очистить нерабочие", "callback_data": "proxy_clean"}],
            [{"text": "◀️ Назад", "callback_data": "main_menu"}]
        ]
    }
    msg = f"🔧 Управление прокси\n\nВсего в пуле: {proxy_count}"
    send_telegram_message(msg, keyboard=keyboard, chat_id=chat_id)

# ==================== Фоновые задачи для прокси ====================
def add_proxies_from_list(proxies, chat_id):
    """Проверяет список прокси и добавляет рабочие в пул"""
    working = []
    total = len(proxies)
    for i, proxy in enumerate(proxies, 1):
        send_telegram_message(f"⏳ Проверка {i}/{total}: {proxy}", chat_id=chat_id)
        proxy_url, ok, ip, speed = test_proxy(proxy)
        if ok:
            add_proxy_to_pool(proxy_url)
            working.append(proxy_url)
            send_telegram_message(f"✅ {proxy} работает (IP: {ip}, {speed}с)", chat_id=chat_id)
        else:
            send_telegram_message(f"❌ {proxy} не работает", chat_id=chat_id)
    
    if working:
        msg = f"🎉 Добавлено {len(working)} рабочих прокси"
    else:
        msg = "❌ Ни одного рабочего прокси не найдено"
    send_telegram_message(msg, chat_id=chat_id)
    send_proxy_menu(chat_id)

def check_all_proxies(chat_id):
    """Проверяет все прокси в текущем пуле и удаляет нерабочие"""
    send_telegram_message("🔄 Начинаю полную проверку пула прокси...", chat_id=chat_id)
    working = check_and_update_proxies()
    msg = f"✅ Проверка завершена. Рабочих прокси: {len(working)}"
    send_telegram_message(msg, chat_id=chat_id)
    send_proxy_menu(chat_id)

def clean_proxies(chat_id):
    """Удаляет нерабочие прокси"""
    send_telegram_message("🧹 Очистка нерабочих прокси...", chat_id=chat_id)
    working = check_and_update_proxies()
    msg = f"✅ Осталось рабочих прокси: {len(working)}"
    send_telegram_message(msg, chat_id=chat_id)
    send_proxy_menu(chat_id)

# ==================== Вебхуки и маршруты ====================

@app.route('/health')
def health():
    """Простой эндпоинт для проверки работы сервера"""
    return "OK", 200

@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'POST':
        Thread(target=handle_update, args=(request.json,)).start()
        return 'OK', 200
    return home()

@app.route('/')
def home():
    with state_lock:
        uptime = int(time.time() - BOT_STATE.get('start_time', time.time()))
        return f"Бот активен. Аптайм: {uptime} сек. Найдено: {BOT_STATE['stats']['total_finds']}"

# ==================== Обработчик обновлений ====================

def handle_update(update):
    """Обрабатывает входящее обновление от Telegram."""
    try:
        if 'callback_query' in update:
            q = update['callback_query']
            data = q['data']
            chat_id = q['from']['id']
            token = TELEGRAM_BOT_TOKEN
            if token:
                requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                              json={'callback_query_id': q['id']})

            if data == 'main_menu':
                send_main_menu(chat_id)
            elif data == 'mode_menu':
                send_mode_menu(chat_id)
            elif data == 'toggle_turbo':
                with state_lock:
                    BOT_STATE['turbo_mode'] = not BOT_STATE['turbo_mode']
                    mode = "🐱‍🏍 ТУРБО" if BOT_STATE['turbo_mode'] else "🐢 Обычный"
                send_telegram_message(f"⚡ Режим изменён: {mode}", chat_id=chat_id)
                send_main_menu(chat_id)
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
                    BOT_STATE['paused'] = not BOT_STATE['paused']
                    status = "⏸ ПАУЗА" if BOT_STATE['paused'] else "▶️ АКТИВЕН"
                send_telegram_message(f"Статус изменён: {status}", chat_id=chat_id)
                send_main_menu(chat_id)
            elif data == 'mode_auto':
                with state_lock:
                    BOT_STATE['mode'] = 'auto'
                send_telegram_message("✅ Режим: автоматический", chat_id=chat_id)
                send_main_menu(chat_id)
            elif data == 'mode_manual':
                with state_lock:
                    if BOT_STATE['selected_brands']:
                        BOT_STATE['mode'] = 'manual'
                        send_telegram_message(f"✅ Режим: ручной ({len(BOT_STATE['selected_brands'])} брендов)", chat_id=chat_id)
                    else:
                        send_telegram_message("⚠️ Сначала выберите бренды!", chat_id=chat_id)
                send_main_menu(chat_id)
            elif data.startswith('toggle_platform_'):
                platform = data.replace('toggle_platform_', '')
                with state_lock:
                    if platform in BOT_STATE['selected_platforms']:
                        BOT_STATE['selected_platforms'].remove(platform)
                    else:
                        BOT_STATE['selected_platforms'].append(platform)
                send_platforms_menu(chat_id)
            elif data.startswith('page_'):
                page = int(data.split('_')[1])
                send_brands_list(page, chat_id)
            elif data.startswith('toggle_'):
                brand = data[7:]
                with state_lock:
                    if brand in BOT_STATE['selected_brands']:
                        BOT_STATE['selected_brands'].remove(brand)
                        send_telegram_message(f"❌ {brand} убран", chat_id=chat_id)
                    else:
                        BOT_STATE['selected_brands'].append(brand)
                        send_telegram_message(f"✅ {brand} добавлен", chat_id=chat_id)
                send_brands_list(0, chat_id)
            elif data == 'select_popular':
                with state_lock:
                    BOT_STATE['selected_brands'] = POPULAR_BRANDS.copy()
                send_telegram_message(f"✅ {len(POPULAR_BRANDS)} популярных брендов", chat_id=chat_id)
                send_select_brands_menu(chat_id)
            elif data == 'random_5':
                import random
                if len(BRAND_MAIN_NAMES) >= 5:
                    rnd = random.sample(BRAND_MAIN_NAMES, 5)
                    with state_lock:
                        BOT_STATE['selected_brands'] = rnd
                    send_telegram_message("✅ 5 случайных брендов", chat_id=chat_id)
                    send_select_brands_menu(chat_id)
                else:
                    send_telegram_message("⚠️ В базе менее 5 брендов", chat_id=chat_id)
            elif data == 'random_10':
                import random
                if len(BRAND_MAIN_NAMES) >= 10:
                    rnd = random.sample(BRAND_MAIN_NAMES, 10)
                    with state_lock:
                        BOT_STATE['selected_brands'] = rnd
                    send_telegram_message("✅ 10 случайных брендов", chat_id=chat_id)
                    send_select_brands_menu(chat_id)
                else:
                    send_telegram_message("⚠️ В базе менее 10 брендов", chat_id=chat_id)
            elif data == 'clear_all':
                with state_lock:
                    BOT_STATE['selected_brands'] = []
                send_telegram_message("🗑 Список очищен", chat_id=chat_id)
                send_select_brands_menu(chat_id)
            elif data.startswith('int_'):
                new_interval = int(data.split('_')[1])
                with state_lock:
                    BOT_STATE['interval'] = new_interval
                send_telegram_message(f"✅ Интервал установлен: {new_interval} мин", chat_id=chat_id)
                send_main_menu(chat_id)
            elif data == 'start_check':
                if BOT_STATE['is_checking']:
                    send_telegram_message("⚠️ Уже выполняется", chat_id=chat_id)
                else:
                    from scheduler import check_all_marketplaces
                    Thread(target=check_all_marketplaces).start()
            
            # Новые обработчики для прокси
            elif data == 'proxy_menu':
                send_proxy_menu(chat_id)
            elif data == 'proxy_add':
                send_telegram_message("📝 Отправьте список прокси (каждый с новой строки).\n"
                                      "Формат: protocol://ip:port (например, http://123.45.67.89:8080 или socks5://...)", 
                                      chat_id=chat_id)
                with state_lock:
                    BOT_STATE['awaiting_proxy'] = True
            elif data == 'proxy_check':
                send_telegram_message("🔄 Проверка прокси, это может занять некоторое время...", chat_id=chat_id)
                Thread(target=check_all_proxies, args=(chat_id,)).start()
            elif data == 'proxy_stats':
                stats = get_proxy_stats()
                msg = (f"📊 Статистика прокси:\n"
                       f"Всего в пуле: {stats['total']}\n"
                       f"Рабочих: {stats['good']}\n"
                       f"Нерабочих: {stats['bad']}\n"
                       f"Текущий индекс: {stats['current_index']}\n"
                       f"Запросов на этом прокси: {stats['requests_this_proxy']}")
                send_telegram_message(msg, chat_id=chat_id)
                send_proxy_menu(chat_id)
            elif data == 'proxy_clean':
                send_telegram_message("🧹 Очистка нерабочих прокси...", chat_id=chat_id)
                Thread(target=clean_proxies, args=(chat_id,)).start()
                
        elif 'message' in update:
            chat_id = update['message']['chat']['id']
            text = update['message'].get('text', '')
            
            # Проверяем, не ожидаем ли мы ввод прокси
            with state_lock:
                awaiting = BOT_STATE.get('awaiting_proxy', False)
            
            if awaiting:
                # Сбрасываем флаг
                with state_lock:
                    BOT_STATE['awaiting_proxy'] = False
                
                # Разбираем список прокси
                lines = text.strip().split('\n')
                proxies = [line.strip() for line in lines if line.strip()]
                
                if not proxies:
                    send_telegram_message("❌ Список пуст. Попробуйте снова.", chat_id=chat_id)
                else:
                    send_telegram_message(f"🔍 Проверяю {len(proxies)} прокси...", chat_id=chat_id)
                    Thread(target=add_proxies_from_list, args=(proxies, chat_id)).start()
                return
            
            # Обработка обычных команд
            if text == '/start':
                send_main_menu(chat_id)
            else:
                send_telegram_message("❌ Неизвестная команда. Используйте /start", chat_id=chat_id)
    except Exception as e:
        logger.error(f"Ошибка в обработчике: {e}")

# Сохраняем функцию отправки в BOT_STATE для использования в scheduler
BOT_STATE['send_to_telegram'] = send_telegram_message
if 'start_time' not in BOT_STATE:
    with state_lock:
        BOT_STATE['start_time'] = time.time()