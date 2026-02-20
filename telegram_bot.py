import json
import time
import requests
from threading import Thread
from flask import Flask, request
import asyncio
import aiohttp

from config import (
    BOT_STATE, state_lock, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    logger, ALL_PLATFORMS, PROXY_POOL
)
from brands import BRAND_MAIN_NAMES, get_variations_for_platform
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

# ==================== АСИНХРОННЫЕ ФУНКЦИИ ДЛЯ ПРОВЕРКИ ПРОКСИ ====================
async def check_proxy_async(session, proxy, semaphore):
    """Проверяет один прокси асинхронно с ограничением параллельных запросов"""
    async with semaphore:
        try:
            if proxy.startswith(('http://', 'https://', 'socks5://')):
                proxy_url = proxy
                display_proxy = proxy
            else:
                proxy_url = f'http://{proxy}'
                display_proxy = proxy
            
            start = time.time()
            async with session.get('http://httpbin.org/ip', 
                                  proxy=proxy_url, 
                                  timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    elapsed = time.time() - start
                    return proxy, True, data.get('origin'), round(elapsed, 2)
        except Exception:
            pass
    return proxy, False, None, None

async def async_send_message(chat_id, text):
    """Обёртка для отправки сообщения из асинхронного кода"""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, send_telegram_message, text, None, None, chat_id)

async def process_proxy_batch(batch, chat_id, batch_num, total_batches):
    """Обрабатывает один батч прокси"""
    working = []
    conn = aiohttp.TCPConnector(limit=50, limit_per_host=10, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=5)
    semaphore = asyncio.Semaphore(50)
    
    await async_send_message(chat_id, f"📦 Проверяю батч {batch_num}/{total_batches} ({len(batch)} прокси)...")
    
    async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
        tasks = []
        for proxy in batch:
            task = check_proxy_async(session, proxy, semaphore)
            tasks.append(task)
        
        for i, task in enumerate(asyncio.as_completed(tasks), 1):
            proxy, ok, ip, speed = await task
            if ok:
                working.append(proxy)
                await async_send_message(chat_id, f"✅ {i}/{len(batch)}: {proxy} работает (IP: {ip}, {speed}с)")
                add_proxy_to_pool(proxy)
            else:
                await async_send_message(chat_id, f"❌ {i}/{len(batch)}: {proxy} не работает")
    
    return working

async def async_check_proxies(proxies, chat_id):
    """Главная асинхронная функция проверки прокси"""
    start_time = time.time()
    
    await async_send_message(chat_id, 
        f"🔄 Начинаю асинхронную проверку {len(proxies)} прокси...\n"
        f"⚡ Результаты будут появляться по мере проверки."
    )
    
    batch_size = 50
    all_working = []
    total_batches = (len(proxies) + batch_size - 1) // batch_size
    
    for i in range(0, len(proxies), batch_size):
        batch = proxies[i:i+batch_size]
        batch_num = i//batch_size + 1
        working = await process_proxy_batch(batch, chat_id, batch_num, total_batches)
        all_working.extend(working)
    
    elapsed = time.time() - start_time
    await async_send_message(chat_id, 
        f"🎉 Асинхронная проверка завершена за {elapsed:.1f}с!\n"
        f"✅ Рабочих прокси: {len(all_working)}/{len(proxies)}\n"
        f"📊 Процент успеха: {len(all_working)/len(proxies)*100:.1f}%"
    )
    send_proxy_menu(chat_id)

def add_proxies_from_list(proxies, chat_id):
    """Запускает асинхронную проверку прокси в отдельном потоке"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(async_check_proxies(proxies, chat_id))
    finally:
        loop.close()

def check_all_proxies(chat_id):
    """Проверяет все прокси в текущем пуле"""
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
    """Удаляет нерабочие прокси"""
    send_telegram_message("🧹 Очистка нерабочих прокси...", chat_id=chat_id)
    working = check_and_update_proxies()
    send_telegram_message(f"✅ Осталось рабочих прокси: {len(working)}", chat_id=chat_id)
    send_proxy_menu(chat_id)

# ==================== Вебхуки и маршруты ====================
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
        # СПИСОК РАЗРЕШЁННЫХ ПОЛЬЗОВАТЕЛЕЙ (добавляй сюда новые ID)
        ALLOWED_USER_IDS = [945746201, 1308690114]  # твой ID и ID друзей
        
        # Проверяем, откуда пришло обновление
        if 'callback_query' in update:
            user_id = update['callback_query']['from']['id']
        elif 'message' in update:
            user_id = update['message']['from']['id']
        else:
            return  # Непонятный тип обновления
        
        # Если пользователь не в списке разрешённых – игнорируем
        if user_id not in ALLOWED_USER_IDS:
            logger.warning(f"Заблокирован доступ для user_id: {user_id}")
            return
        
        # ДАЛЬШЕ ВЕСЬ ОБЫЧНЫЙ КОД ОБРАБОТКИ
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
                    BOT_STATE['mode'] = 'manual'
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
                    if BOT_STATE['selected_brands']:
                        BOT_STATE['mode'] = 'manual'
                    else:
                        BOT_STATE['mode'] = 'auto'
                send_brands_list(0, chat_id)
            elif data == 'clear_all':
                with state_lock:
                    BOT_STATE['selected_brands'] = []
                    BOT_STATE['mode'] = 'auto'
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
            elif data == 'proxy_menu':
                send_proxy_menu(chat_id)
            elif data == 'proxy_add':
                send_telegram_message("📝 Отправьте список прокси (каждый с новой строки).\n"
                                      "Формат: protocol://ip:port (например, http://123.45.67.89:8080 или socks5://...)",
                                      chat_id=chat_id)
                with state_lock:
                    BOT_STATE['awaiting_proxy'] = True
            elif data == 'proxy_check':
                send_telegram_message("🔄 Проверка прокси...", chat_id=chat_id)
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

            with state_lock:
                awaiting = BOT_STATE.get('awaiting_proxy', False)

            if awaiting:
                with state_lock:
                    BOT_STATE['awaiting_proxy'] = False
                lines = text.strip().split('\n')
                proxies = [line.strip() for line in lines if line.strip()]
                if not proxies:
                    send_telegram_message("❌ Список пуст. Попробуйте снова.", chat_id=chat_id)
                else:
                    send_telegram_message(f"🔍 Проверяю {len(proxies)} прокси...", chat_id=chat_id)
                    Thread(target=add_proxies_from_list, args=(proxies, chat_id)).start()
                return

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