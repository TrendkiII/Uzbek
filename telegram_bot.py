import os
import json
import time
import asyncio
from threading import Thread

import requests
from flask import Flask, request

from config import (
    BOT_STATE, state_lock, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    logger, ALL_PLATFORMS, PROXY_POOL, stop_event
)
from brands import BRAND_MAIN_NAMES, get_variations_for_platform, BRAND_GROUPS, detect_brand_from_title
from scheduler_common import run_search
from scheduler import check_all_marketplaces
from utils import (
    test_proxy, add_proxy_to_pool, check_and_update_proxies,
    get_proxy_stats, mark_proxy_bad_str
)
from database import (
    get_items_by_brand_main, get_brands_stats, check_item_status,
    get_stats, get_all_brands_from_db
)

app = Flask(__name__)

# ==================== Константы ====================
ALLOWED_USER_IDS = [int(id) for id in os.environ.get("ALLOWED_USER_IDS", "945746201,1600234834").split(",")]

# ==================== Вспомогательные функции отправки ====================

def send_telegram_message(text, photo_url=None, keyboard=None, chat_id=None, parse_mode='HTML'):
    """Отправляет сообщение в Telegram с повторными попытками"""
    token = TELEGRAM_BOT_TOKEN
    if not token:
        logger.error("Нет TELEGRAM_BOT_TOKEN")
        return False
    if not chat_id:
        chat_id = TELEGRAM_CHAT_ID
        if not chat_id:
            logger.error("Нет chat_id")
            return False

    url = f"https://api.telegram.org/bot{token}/"
    method = 'sendPhoto' if photo_url else 'sendMessage'
    payload = {
        'chat_id': chat_id,
        'parse_mode': parse_mode,
        'disable_web_page_preview': False
    }
    if photo_url:
        payload['photo'] = photo_url
        payload['caption'] = text
    else:
        payload['text'] = text
    if keyboard:
        payload['reply_markup'] = json.dumps(keyboard)

    for attempt in range(3):
        try:
            r = requests.post(url + method, data=payload, timeout=10)
            if r.status_code == 200:
                return True
            logger.warning(f"Telegram API error {r.status_code}, attempt {attempt+1}")
        except Exception as e:
            logger.warning(f"Telegram send error: {e}, attempt {attempt+1}")
        time.sleep(2)
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
    payload = {'chat_id': chat_id, 'media': json.dumps(media_group)}
    try:
        requests.post(url, data=payload, timeout=15)
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки альбома: {e}")
        return False

def answer_callback(callback_query_id, text=None):
    if TELEGRAM_BOT_TOKEN:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
            json={'callback_query_id': callback_query_id, 'text': text}
        )

# ==================== Меню (строители клавиатур) ====================

def build_main_menu():
    with state_lock:
        turbo_status = "🐱‍🏍 ТУРБО" if BOT_STATE.get('turbo_mode') else "🐢 Обычный"
        pause_status = "⏸ ПАУЗА" if BOT_STATE['paused'] else "▶️ АКТИВЕН"
        platforms = ", ".join(BOT_STATE['selected_platforms']) if BOT_STATE['selected_platforms'] else "Нет"
        brands_info = f"Выбрано: {len(BOT_STATE['selected_brands'])}" if BOT_STATE['selected_brands'] else "Бренды не выбраны"
        proxy_count = len(PROXY_POOL)
        msg = (
            f"🤖 Мониторинг\n"
            f"Режим: {BOT_STATE['mode']}\n"
            f"Турбо: {'Вкл' if BOT_STATE.get('turbo_mode') else 'Выкл'}\n"
            f"Статус: {pause_status}\n"
            f"Площадки: {platforms}\n"
            f"{brands_info}\n"
            f"Прокси в пуле: {proxy_count}\n"
            f"Проверок: {BOT_STATE['stats']['total_checks']}\n"
            f"Найдено: {BOT_STATE['stats']['total_finds']}\n"
            f"Последняя: {BOT_STATE['last_check'] or 'никогда'}"
        )
    keyboard = {
        "inline_keyboard": [
            [{"text": "🚀 Обычный поиск", "callback_data": "start_check"}],
            [{"text": "⚡ СУПЕР-ТУРБО", "callback_data": "start_super_turbo"}],
            [{"text": "⚙️ Режим работы", "callback_data": "mode_menu"}],
            [{"text": f"⚡ Режим: {turbo_status}", "callback_data": "toggle_turbo"}],
            [{"text": "🌐 Выбор площадок", "callback_data": "platforms_menu"}],
            [{"text": "📊 Статистика", "callback_data": "stats"}],
            [{"text": "📋 Список брендов", "callback_data": "brands_list"}],
            [{"text": "⏱ Интервал", "callback_data": "interval"}],
            [{"text": "🔄 Выбрать бренды", "callback_data": "select_brands_menu"}],
            [{"text": "📦 Мои находки", "callback_data": "myitems_menu"}],
            [{"text": "🔧 Управление прокси", "callback_data": "proxy_menu"}],
            [{"text": "⏹️ Остановить проверку", "callback_data": "stop_check"}],
            [{"text": "⏸ Пауза / ▶️ Продолжить", "callback_data": "toggle_pause"}]
        ]
    }
    return msg, keyboard

def build_mode_menu():
    return "⚙️ Выберите режим:", {
        "inline_keyboard": [
            [{"text": "🤖 Авто (все вариации)", "callback_data": "mode_auto"}],
            [{"text": "👆 Ручной (выбранные бренды)", "callback_data": "mode_manual"}],
            [{"text": "◀️ Назад", "callback_data": "main_menu"}]
        ]
    }

def build_platforms_menu():
    keyboard = {"inline_keyboard": []}
    with state_lock:
        selected = BOT_STATE['selected_platforms']
    for p in ALL_PLATFORMS:
        mark = "✅ " if p in selected else ""
        keyboard["inline_keyboard"].append([{"text": f"{mark}{p}", "callback_data": f"toggle_platform_{p}"}])
    keyboard["inline_keyboard"].append([{"text": "◀️ Назад", "callback_data": "main_menu"}])
    return "🌐 Выберите площадки:", keyboard

def build_brands_list(page=0):
    per_page = 8
    start = page * per_page
    end = start + per_page
    total = len(BRAND_MAIN_NAMES)
    pages = (total + per_page - 1) // per_page
    slice_names = BRAND_MAIN_NAMES[start:end]

    keyboard = {"inline_keyboard": []}
    with state_lock:
        selected_brands = BOT_STATE['selected_brands']
    for name in slice_names:
        mark = "✅ " if name in selected_brands else ""
        keyboard["inline_keyboard"].append([{"text": f"{mark}{name}", "callback_data": f"toggle_{name}"}])

    nav = []
    if page > 0:
        nav.append({"text": "◀️", "callback_data": f"brands_page_{page-1}"})
    nav.append({"text": f"{page+1}/{pages}", "callback_data": "noop"})
    if page < pages-1:
        nav.append({"text": "▶️", "callback_data": f"brands_page_{page+1}"})
    if nav:
        keyboard["inline_keyboard"].append(nav)

    actions = []
    if selected_brands:
        actions.append({"text": "❌ Очистить все", "callback_data": "clear_all_confirm"})
    actions.append({"text": "◀️ Назад", "callback_data": "main_menu"})
    keyboard["inline_keyboard"].append(actions)

    var_count = 0
    with state_lock:
        if BOT_STATE['selected_platforms'] and selected_brands:
            sample_platform = BOT_STATE['selected_platforms'][0]
            vars_list = []
            for brand in selected_brands:
                vars_list.extend(get_variations_for_platform(brand, sample_platform))
            var_count = len(set(vars_list))
    msg = f"📋 Выбрано: {len(selected_brands)} / вариаций: {var_count} (для первой площадки)"
    return msg, keyboard

def build_select_brands_menu():
    with state_lock:
        selected = len(BOT_STATE['selected_brands'])
    return f"🔄 Выбрано: {selected}", {
        "inline_keyboard": [
            [{"text": "📋 Выбрать из списка", "callback_data": "brands_list"}],
            [{"text": "❌ Очистить все", "callback_data": "clear_all_confirm"}],
            [{"text": "◀️ Назад", "callback_data": "main_menu"}]
        ]
    }

def build_stats():
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
    return msg, {"inline_keyboard": [[{"text": "◀️ Назад", "callback_data": "main_menu"}]]}

def build_interval_menu():
    with state_lock:
        current = BOT_STATE['interval']
    return f"⏱ Текущий интервал: {current} мин", {
        "inline_keyboard": [
            [{"text": "15 мин", "callback_data": "int_15"}, {"text": "30 мин", "callback_data": "int_30"}],
            [{"text": "1 час", "callback_data": "int_60"}, {"text": "3 часа", "callback_data": "int_180"}],
            [{"text": "6 часов", "callback_data": "int_360"}],
            [{"text": "12 часов", "callback_data": "int_720"}],
            [{"text": "◀️ Назад", "callback_data": "main_menu"}]
        ]
    }

def build_proxy_menu():
    with state_lock:
        proxy_count = len(PROXY_POOL)
    return f"🔧 Управление прокси\n\nВсего в пуле: {proxy_count}", {
        "inline_keyboard": [
            [{"text": "➕ Добавить прокси", "callback_data": "proxy_add"}],
            [{"text": "🔍 Проверить все", "callback_data": "proxy_check"}],
            [{"text": "📊 Статистика", "callback_data": "proxy_stats"}],
            [{"text": "🗑 Очистить нерабочие", "callback_data": "proxy_clean"}],
            [{"text": "◀️ Назад", "callback_data": "main_menu"}]
        ]
    }

def build_myitems_menu():
    return "📦 Мои найденные товары\n\nВыберите действие:", {
        "inline_keyboard": [
            [{"text": "📦 По брендам", "callback_data": "myitems_brands"}],
            [{"text": "📊 Статистика по брендам", "callback_data": "myitems_stats"}],
            [{"text": "◀️ Назад", "callback_data": "main_menu"}]
        ]
    }

def build_brands_list_for_items(page=0):
    stats = get_brands_stats()
    if not stats:
        return "❌ В базе пока нет товаров", {"inline_keyboard": [[{"text": "◀️ Назад", "callback_data": "myitems_menu"}]]}
    per_page = 8
    start = page * per_page
    end = start + per_page
    total = len(stats)
    pages = (total + per_page - 1) // per_page
    slice_stats = stats[start:end]

    keyboard = {"inline_keyboard": []}
    for stat in slice_stats:
        active = stat['active'] or 0
        total_items = stat['total']
        status = f"✅ {active}/{total_items}" if active > 0 else f"❌ 0/{total_items}"
        keyboard["inline_keyboard"].append([
            {"text": f"{stat['brand']} - {status}", "callback_data": f"showbrand_{stat['brand']}"}
        ])

    nav = []
    if page > 0:
        nav.append({"text": "◀️", "callback_data": f"itembrands_page_{page-1}"})
    nav.append({"text": f"{page+1}/{pages}", "callback_data": "noop"})
    if page < pages-1:
        nav.append({"text": "▶️", "callback_data": f"itembrands_page_{page+1}"})
    if nav:
        keyboard["inline_keyboard"].append(nav)

    actions = [{"text": "◀️ Назад", "callback_data": "myitems_menu"}]
    keyboard["inline_keyboard"].append(actions)
    return "📋 Выберите бренд для просмотра товаров:", keyboard

def build_items_by_brand(brand, page=0, show_sold=False):
    brand_clean = brand.strip()
    items = get_items_by_brand_main(brand_clean, limit=50, include_sold=show_sold)
    if not items:
        return f"❌ Нет товаров для бренда {brand_clean}", {"inline_keyboard": [[{"text": "◀️ Назад", "callback_data": "myitems_brands"}]]}
    per_page = 5
    start = page * per_page
    end = start + per_page
    total = len(items)
    pages = (total + per_page - 1) // per_page
    slice_items = items[start:end]

    msg = f"📦 <b>{brand_clean}</b> - товары {start+1}-{min(end, total)} из {total}\n\n"
    for i, item in enumerate(slice_items, start+1):
        status = "✅" if item['is_active'] else "💰 ПРОДАН"
        msg += f"{i}. {status} <a href='{item['url']}'>{item['title'][:50]}</a>\n"
        msg += f"   💰 {item['price']} | 🏷 {item['source']}\n\n"

    keyboard = {"inline_keyboard": []}
    nav = []
    if page > 0:
        nav.append({"text": "◀️", "callback_data": f"brandpage_{brand_clean}_{page-1}_{int(show_sold)}"})
    nav.append({"text": f"{page+1}/{pages}", "callback_data": "noop"})
    if page < pages-1:
        nav.append({"text": "▶️", "callback_data": f"brandpage_{brand_clean}_{page+1}_{int(show_sold)}"})
    if nav:
        keyboard["inline_keyboard"].append(nav)

    toggle_text = "🔄 Показать все" if not show_sold else "✅ Только активные"
    toggle_data = f"brandpage_{brand_clean}_0_{0 if show_sold else 1}"
    actions = [
        [{"text": toggle_text, "callback_data": toggle_data}],
        [{"text": "🔄 Проверить проданные", "callback_data": f"checksold_{brand_clean}"}],
        [{"text": "📋 Все бренды", "callback_data": "myitems_brands"}],
        [{"text": "◀️ Главное меню", "callback_data": "main_menu"}]
    ]
    keyboard["inline_keyboard"].extend(actions)
    return msg, keyboard

def build_brands_stats():
    stats = get_brands_stats()
    if not stats:
        return "❌ В базе пока нет товаров", {"inline_keyboard": [[{"text": "◀️ Назад", "callback_data": "myitems_menu"}]]}
    msg = "📊 <b>Статистика по брендам</b>\n\n"
    total_all = 0
    active_all = 0
    for stat in stats:
        active = stat['active'] or 0
        total_items = stat['total']
        total_all += total_items
        active_all += active
        msg += f"• <b>{stat['brand']}</b>: {active}/{total_items} активных\n"
    msg += f"\n<b>Всего:</b> {active_all}/{total_all} товаров"
    return msg, {
        "inline_keyboard": [
            [{"text": "📋 По брендам", "callback_data": "myitems_brands"}],
            [{"text": "◀️ Назад", "callback_data": "myitems_menu"}]
        ]
    }

# ==================== Обработчики callback'ов ====================

def handle_callback_main_menu(callback, chat_id):
    msg, kb = build_main_menu()
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_mode_menu(callback, chat_id):
    msg, kb = build_mode_menu()
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_platforms_menu(callback, chat_id):
    msg, kb = build_platforms_menu()
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_toggle_turbo(callback, chat_id):
    with state_lock:
        BOT_STATE['turbo_mode'] = not BOT_STATE['turbo_mode']
        mode = "🐱‍🏍 ТУРБО" if BOT_STATE['turbo_mode'] else "🐢 Обычный"
    send_telegram_message(f"⚡ Режим изменён: {mode}", chat_id=chat_id)
    handle_callback_main_menu(callback, chat_id)

def handle_callback_stats(callback, chat_id):
    msg, kb = build_stats()
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_brands_list(callback, chat_id):
    data = callback['data']
    if data == 'brands_list':
        page = 0
    else:
        page = int(data.split('_')[-1])
    msg, kb = build_brands_list(page)
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_select_brands_menu(callback, chat_id):
    msg, kb = build_select_brands_menu()
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_interval(callback, chat_id):
    msg, kb = build_interval_menu()
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_toggle_pause(callback, chat_id):
    with state_lock:
        BOT_STATE['paused'] = not BOT_STATE['paused']
        status = "⏸ ПАУЗА" if BOT_STATE['paused'] else "▶️ АКТИВЕН"
    send_telegram_message(f"Статус изменён: {status}", chat_id=chat_id)
    handle_callback_main_menu(callback, chat_id)

def handle_callback_mode_auto(callback, chat_id):
    with state_lock:
        BOT_STATE['mode'] = 'auto'
    send_telegram_message("✅ Режим: автоматический", chat_id=chat_id)
    handle_callback_main_menu(callback, chat_id)

def handle_callback_mode_manual(callback, chat_id):
    with state_lock:
        if BOT_STATE['selected_brands']:
            BOT_STATE['mode'] = 'manual'
            send_telegram_message(f"✅ Режим: ручной ({len(BOT_STATE['selected_brands'])} брендов)", chat_id=chat_id)
        else:
            send_telegram_message("⚠️ Сначала выберите бренды!", chat_id=chat_id)
    handle_callback_main_menu(callback, chat_id)

def handle_callback_toggle_platform(callback, chat_id):
    platform = callback['data'].replace('toggle_platform_', '')
    with state_lock:
        if platform in BOT_STATE['selected_platforms']:
            BOT_STATE['selected_platforms'].remove(platform)
        else:
            BOT_STATE['selected_platforms'].append(platform)
    msg, kb = build_platforms_menu()
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_toggle_brand(callback, chat_id):
    brand = callback['data'][7:]
    with state_lock:
        if brand in BOT_STATE['selected_brands']:
            BOT_STATE['selected_brands'].remove(brand)
            notification = f"❌ {brand} убран"
        else:
            BOT_STATE['selected_brands'].append(brand)
            notification = f"✅ {brand} добавлен"
        if BOT_STATE['selected_brands']:
            BOT_STATE['mode'] = 'manual'
        else:
            BOT_STATE['mode'] = 'auto'
    send_telegram_message(notification, chat_id=chat_id)
    msg, kb = build_brands_list(0)
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_clear_all_confirm(callback, chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ Да, очистить", "callback_data": "clear_all_yes"}],
            [{"text": "❌ Нет", "callback_data": "brands_list"}]
        ]
    }
    send_telegram_message("⚠️ Вы уверены, что хотите очистить список выбранных брендов?", keyboard=keyboard, chat_id=chat_id)

def handle_callback_clear_all_yes(callback, chat_id):
    with state_lock:
        BOT_STATE['selected_brands'] = []
        BOT_STATE['mode'] = 'auto'
    send_telegram_message("🗑 Список брендов очищен", chat_id=chat_id)
    handle_callback_main_menu(callback, chat_id)

def handle_callback_int(callback, chat_id):
    new_interval = int(callback['data'].split('_')[1])
    with state_lock:
        BOT_STATE['interval'] = new_interval
    send_telegram_message(f"✅ Интервал установлен: {new_interval} мин", chat_id=chat_id)
    handle_callback_main_menu(callback, chat_id)

def handle_callback_start_check(callback, chat_id):
    if BOT_STATE.get('is_checking', False):  # можно использовать, но у нас нет глобального is_checking
        send_telegram_message("⚠️ Проверка уже выполняется", chat_id=chat_id)
    else:
        stop_event.clear()
        send_telegram_message("⏳ Запускаю обычный поиск...", chat_id=chat_id)
        Thread(target=check_all_marketplaces, args=(chat_id,)).start()

def handle_callback_start_super_turbo(callback, chat_id):
    if BOT_STATE.get('is_checking', False):
        send_telegram_message("⚠️ Проверка уже выполняется", chat_id=chat_id)
        return
    stop_event.clear()
    with state_lock:
        mode = BOT_STATE['mode']
        selected_brands = BOT_STATE['selected_brands'].copy()
        platforms = BOT_STATE['selected_platforms'].copy()
    if mode == 'auto':
        all_vars = []
        for group in BRAND_GROUPS:
            for typ in ['latin', 'jp', 'cn', 'universal']:
                if typ in group['variations']:
                    all_vars.extend(group['variations'][typ])
        keywords = list(set(all_vars))[:50]  # ограничим 50 ключами
    else:
        if not selected_brands:
            send_telegram_message("⚠️ В ручном режиме нужно выбрать бренды!", chat_id=chat_id)
            return
        if not platforms:
            send_telegram_message("⚠️ Не выбраны площадки!", chat_id=chat_id)
            return
        sample_platform = platforms[0]
        keywords = []
        for brand in selected_brands:
            keywords.extend(get_variations_for_platform(brand, sample_platform))
        keywords = list(set(keywords))[:50]  # тоже ограничим
    if not keywords:
        send_telegram_message("⚠️ Нет ключевых слов для поиска", chat_id=chat_id)
        return
    # Для супер-турбо используем 10 воркеров
    send_telegram_message(f"⚡ Запускаю супер-турбо поиск по {len(keywords)} ключам...", chat_id=chat_id)
    Thread(target=run_search, args=(keywords, platforms, chat_id, 10)).start()

def handle_callback_stop_check(callback, chat_id):
    stop_event.set()
    send_telegram_message("⏹️ Сигнал остановки отправлен. Проверка будет прервана после текущих запросов.", chat_id=chat_id)

def handle_callback_proxy_menu(callback, chat_id):
    msg, kb = build_proxy_menu()
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_proxy_add(callback, chat_id):
    send_telegram_message(
        "📝 Отправьте список прокси (каждый с новой строки) или файл .txt/.json.\n"
        "Формат: protocol://ip:port (например, http://123.45.67.89:8080 или socks5://...)\n"
        "Если отправляете файл, просто прикрепите его.",
        chat_id=chat_id
    )
    with state_lock:
        BOT_STATE['awaiting_proxy'] = True

def handle_callback_proxy_check(callback, chat_id):
    send_telegram_message("🔄 Проверка прокси...", chat_id=chat_id)
    Thread(target=check_all_proxies, args=(chat_id,)).start()

def handle_callback_proxy_stats(callback, chat_id):
    stats = get_proxy_stats()
    msg = (f"📊 Статистика прокси:\n"
           f"Всего в пуле: {stats['total']}\n"
           f"Рабочих: {stats['good']}\n"
           f"Нерабочих: {stats['bad']}\n"
           f"Текущий индекс: {stats['current_index']}\n"
           f"Запросов на этом прокси: {stats['requests_this_proxy']}")
    send_telegram_message(msg, chat_id=chat_id)
    handle_callback_proxy_menu(callback, chat_id)

def handle_callback_proxy_clean(callback, chat_id):
    send_telegram_message("🧹 Очистка нерабочих прокси...", chat_id=chat_id)
    Thread(target=clean_proxies, args=(chat_id,)).start()

def handle_callback_myitems_menu(callback, chat_id):
    msg, kb = build_myitems_menu()
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_myitems_brands(callback, chat_id):
    data = callback['data']
    if data == 'myitems_brands':
        page = 0
    else:
        page = int(data.split('_')[-1])
    msg, kb = build_brands_list_for_items(page)
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_myitems_stats(callback, chat_id):
    msg, kb = build_brands_stats()
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_showbrand(callback, chat_id):
    brand = callback['data'][10:]
    msg, kb = build_items_by_brand(brand, 0, show_sold=False)
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_brandpage(callback, chat_id):
    parts = callback['data'].split('_')
    brand = '_'.join(parts[1:-2])
    page = int(parts[-2])
    show_sold = bool(int(parts[-1]))
    msg, kb = build_items_by_brand(brand, page, show_sold)
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

def handle_callback_checksold(callback, chat_id):
    brand = callback['data'][10:]
    send_telegram_message(f"🔄 Проверяю товары бренда {brand} на статус 'продан'...", chat_id=chat_id)
    Thread(target=check_sold_for_brand, args=(brand, chat_id)).start()

def handle_callback_noop(callback, chat_id):
    pass

# Диспетчер callback'ов
CALLBACK_HANDLERS = {
    'main_menu': handle_callback_main_menu,
    'mode_menu': handle_callback_mode_menu,
    'platforms_menu': handle_callback_platforms_menu,
    'toggle_turbo': handle_callback_toggle_turbo,
    'stats': handle_callback_stats,
    'brands_list': handle_callback_brands_list,
    'select_brands_menu': handle_callback_select_brands_menu,
    'interval': handle_callback_interval,
    'toggle_pause': handle_callback_toggle_pause,
    'mode_auto': handle_callback_mode_auto,
    'mode_manual': handle_callback_mode_manual,
    'start_check': handle_callback_start_check,
    'start_super_turbo': handle_callback_start_super_turbo,
    'stop_check': handle_callback_stop_check,
    'proxy_menu': handle_callback_proxy_menu,
    'proxy_add': handle_callback_proxy_add,
    'proxy_check': handle_callback_proxy_check,
    'proxy_stats': handle_callback_proxy_stats,
    'proxy_clean': handle_callback_proxy_clean,
    'myitems_menu': handle_callback_myitems_menu,
    'myitems_brands': handle_callback_myitems_brands,
    'myitems_stats': handle_callback_myitems_stats,
    'clear_all_confirm': handle_callback_clear_all_confirm,
    'clear_all_yes': handle_callback_clear_all_yes,
    'noop': handle_callback_noop,
}

PREFIX_HANDLERS = {
    'toggle_platform_': handle_callback_toggle_platform,
    'toggle_': handle_callback_toggle_brand,
    'int_': handle_callback_int,
    'brands_page_': handle_callback_brands_list,
    'itembrands_page_': handle_callback_myitems_brands,
    'showbrand_': handle_callback_showbrand,
    'brandpage_': handle_callback_brandpage,
    'checksold_': handle_callback_checksold,
}

# ==================== Обработчик сообщений ====================

async def process_proxies_batch(proxies, chat_id):
    """Асинхронно проверяет пачку прокси (до 50) с отчётом о прогрессе"""
    total = len(proxies)
    working = []
    batch_size = 10
    for i in range(0, total, batch_size):
        batch = proxies[i:i+batch_size]
        tasks = [test_proxy_async(p) for p in batch]
        results = await asyncio.gather(*tasks)
        for proxy, ok, ip, speed in results:
            if ok:
                working.append(proxy)
                add_proxy_to_pool(proxy)
                await asyncio.get_running_loop().run_in_executor(
                    None, send_telegram_message, f"✅ {proxy} работает (IP: {ip}, {speed}с)", None, None, chat_id
                )
            else:
                await asyncio.get_running_loop().run_in_executor(
                    None, send_telegram_message, f"❌ {proxy} не работает", None, None, chat_id
                )
        # после каждой пачки отправляем прогресс
        await asyncio.get_running_loop().run_in_executor(
            None, send_telegram_message, f"⏳ Проверено {min(i+batch_size, total)}/{total}", None, None, chat_id
        )
    return working

def handle_proxy_file_download(file_id, chat_id):
    """Скачивает файл с прокси и возвращает список строк"""
    token = TELEGRAM_BOT_TOKEN
    if not token:
        return None
    r = requests.get(f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}")
    if r.status_code != 200:
        send_telegram_message("❌ Не удалось получить файл", chat_id=chat_id)
        return None
    file_path = r.json()['result']['file_path']
    file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    r = requests.get(file_url)
    if r.status_code != 200:
        send_telegram_message("❌ Не удалось скачать файл", chat_id=chat_id)
        return None
    content = r.text
    lines = []
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            lines.append(line)
    return lines

def handle_message(update):
    chat_id = update['message']['chat']['id']
    text = update['message'].get('text', '')
    document = update['message'].get('document')

    with state_lock:
        awaiting = BOT_STATE.get('awaiting_proxy', False)

    if awaiting:
        with state_lock:
            BOT_STATE['awaiting_proxy'] = False

        proxies = []
        if document:
            file_id = document['file_id']
            send_telegram_message("📥 Загружаю файл с прокси...", chat_id=chat_id)
            proxies = handle_proxy_file_download(file_id, chat_id)
            if proxies is None:
                return
        else:
            lines = text.strip().split('\n')
            proxies = [line.strip() for line in lines if line.strip()]

        if not proxies:
            send_telegram_message("❌ Список пуст. Попробуйте снова.", chat_id=chat_id)
            return

        send_telegram_message(f"🔍 Проверяю {len(proxies)} прокси (это может занять некоторое время)...", chat_id=chat_id)
        def run_check():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                working = loop.run_until_complete(process_proxies_batch(proxies, chat_id))
                msg = f"✅ Проверка завершена. Рабочих прокси: {len(working)}/{len(proxies)}"
                send_telegram_message(msg, chat_id=chat_id)
                msg, kb = build_main_menu()
                send_telegram_message(msg, keyboard=kb, chat_id=chat_id)
            finally:
                loop.close()
        Thread(target=run_check).start()
        return

    if text == '/start':
        handle_callback_main_menu(None, chat_id)
    else:
        send_telegram_message("❌ Неизвестная команда. Используйте /start", chat_id=chat_id)

def check_all_proxies(chat_id):
    with state_lock:
        proxies = PROXY_POOL.copy()
    if not proxies:
        send_telegram_message("❌ Пул прокси пуст", chat_id=chat_id)
        send_proxy_menu(chat_id)
        return
    send_telegram_message(f"🔄 Начинаю проверку всех {len(proxies)} прокси в пуле...", chat_id=chat_id)
    working = check_and_update_proxies()
    send_telegram_message(f"✅ Проверка завершена. Рабочих прокси: {len(working)}", chat_id=chat_id)
    send_proxy_menu(chat_id)

def clean_proxies(chat_id):
    send_telegram_message("🧹 Очистка нерабочих прокси...", chat_id=chat_id)
    working = check_and_update_proxies()
    send_telegram_message(f"✅ Осталось рабочих прокси: {len(working)}", chat_id=chat_id)
    send_proxy_menu(chat_id)

def send_proxy_menu(chat_id):
    msg, kb = build_proxy_menu()
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

# ==================== Проверка проданных для бренда ====================

def check_sold_for_brand(brand, chat_id):
    from database import get_items_by_brand_main, check_item_status
    from utils import make_request
    from bs4 import BeautifulSoup

    items = get_items_by_brand_main(brand, limit=100, include_sold=False)
    if not items:
        send_telegram_message(f"❌ Нет активных товаров для бренда {brand}", chat_id=chat_id)
        return

    send_telegram_message(f"🔄 Проверяю {len(items)} товаров бренда {brand}...", chat_id=chat_id)

    sold_count = 0
    active_count = 0
    error_count = 0

    for i, item in enumerate(items, 1):
        try:
            if i % 10 == 0:
                send_telegram_message(f"⏳ Проверено {i}/{len(items)}...", chat_id=chat_id)

            resp = make_request(item['url'])
            if not resp:
                error_count += 1
                continue

            soup = BeautifulSoup(resp.text, 'lxml')
            is_sold = False

            if item['source'] == 'Mercari JP':
                sold_indicators = soup.select('[class*="sold"], [class*="SOLD"], .item-sold, .sold-out')
                if sold_indicators or "売り切れ" in resp.text:
                    is_sold = True
            elif item['source'] == 'eBay':
                if "This item is out of stock" in resp.text or "Sold" in resp.text:
                    is_sold = True
            elif item['source'] == 'Yahoo Auction':
                if "終了" in resp.text or "ended" in resp.text.lower():
                    is_sold = True
            elif '2nd Street' in item['source']:
                if "SOLD OUT" in resp.text or "売り切れ" in resp.text:
                    is_sold = True

            if is_sold:
                check_item_status(item['id'], False)
                sold_count += 1
            else:
                check_item_status(item['id'], True)
                active_count += 1

            time.sleep(0.5)
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке товара {item.get('id')}: {e}")
            error_count += 1

    msg = (
        f"📊 Результаты проверки бренда {brand}:\n"
        f"✅ Активных: {active_count}\n"
        f"💰 Проданных: {sold_count}\n"
        f"❌ Ошибок: {error_count}\n"
        f"Всего проверено: {len(items)}"
    )
    send_telegram_message(msg, chat_id=chat_id)
    msg, kb = build_items_by_brand(brand, 0, show_sold=False)
    send_telegram_message(msg, keyboard=kb, chat_id=chat_id)

# ==================== Вебхуки и маршруты Flask ====================

@app.route('/health', methods=['GET'])
def health():
    return "OK", 200

@app.route('/', methods=['GET'])
def home():
    return "Bot is alive", 200

@app.route('/', methods=['POST'])
def webhook():
    Thread(target=handle_update, args=(request.json,)).start()
    return 'OK', 200

# ==================== Обработчик обновлений ====================

def handle_update(update):
    try:
        if 'callback_query' in update:
            user_id = update['callback_query']['from']['id']
        elif 'message' in update:
            user_id = update['message']['from']['id']
        else:
            return
        if user_id not in ALLOWED_USER_IDS:
            logger.warning(f"Заблокирован доступ для user_id: {user_id}")
            return

        if 'callback_query' in update:
            q = update['callback_query']
            data = q['data']
            chat_id = q['from']['id']
            answer_callback(q['id'])

            handler = CALLBACK_HANDLERS.get(data)
            if handler:
                handler(q, chat_id)
                return
            for prefix, h in PREFIX_HANDLERS.items():
                if data.startswith(prefix):
                    h(q, chat_id)
                    return
            logger.warning(f"Неизвестный callback: {data}")
        elif 'message' in update:
            handle_message(update)
    except Exception as e:
        logger.error(f"Ошибка в обработчике: {e}")

# Сохраняем функцию отправки в BOT_STATE
BOT_STATE['send_to_telegram'] = send_telegram_message