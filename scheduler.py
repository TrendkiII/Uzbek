import time
import random
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import (
    BOT_STATE, state_lock, logger, MAX_WORKERS, ITEMS_PER_PAGE,
    MIN_DELAY_BETWEEN_REQUESTS, MAX_DELAY_BETWEEN_REQUESTS,
    MIN_DELAY_BETWEEN_BRANDS, MAX_DELAY_BETWEEN_BRANDS
)
from brands import expand_selected_brands_for_platforms, BRAND_GROUPS
from parsers import PARSERS
from database import add_item
from utils import (
    generate_item_id, human_delay, brand_delay,
    get_proxy_stats
)

def process_new_items(items, platform):
    new_items = []
    for item in items:
        if 'id' not in item:
            item['id'] = generate_item_id(item)
        if add_item(item):
            new_items.append(item)
            with state_lock:
                if platform in BOT_STATE['stats']['platform_stats']:
                    BOT_STATE['stats']['platform_stats'][platform]['finds'] += 1
    return new_items

def check_platform(platform, variations, chat_id=None):
    parser = PARSERS.get(platform)
    if not parser:
        logger.warning(f"Нет парсера для {platform}")
        return []
    
    platform_new_items = []
    turbo = BOT_STATE.get('turbo_mode', False)
    request_count = 0
    
    for var in variations:
        request_count += 1
        logger.info(f"[{platform}] Поиск {request_count}/{len(variations)}: {var}")
        items = parser(var)
        if items:
            new = process_new_items(items, platform)
            platform_new_items.extend(new)
            logger.info(f"[{platform}] Найдено {len(items)} товаров, новых {len(new)}")
        
        if turbo:
            time.sleep(random.uniform(0.5, 1))
        else:
            if request_count % 3 == 0:
                brand_delay()
            else:
                human_delay()
    
    return platform_new_items

def check_all_marketplaces(chat_id=None):
    with state_lock:
        if BOT_STATE['is_checking'] or BOT_STATE['paused']:
            logger.warning("Проверка уже выполняется или бот на паузе")
            return
        BOT_STATE['is_checking'] = True
        platforms = BOT_STATE['selected_platforms'].copy()
        mode = BOT_STATE['mode']
        selected_brands = BOT_STATE['selected_brands'].copy()
        turbo = BOT_STATE.get('turbo_mode', False)

    logger.info(f"🚀 Запуск проверки в режиме {'ТУРБО' if turbo else 'обычном'}")

    if mode == 'auto':
        all_vars = []
        for group in BRAND_GROUPS:
            for typ in ['latin', 'jp', 'cn', 'universal']:
                if typ in group['variations']:
                    all_vars.extend(group['variations'][typ])
        all_vars = list(set(all_vars))
        random.shuffle(all_vars)
        vars_per_platform = {p: all_vars[:30] if turbo else all_vars[:20] for p in platforms}
    else:
        if not selected_brands:
            logger.warning("Ручной режим, но бренды не выбраны")
            with state_lock:
                BOT_STATE['is_checking'] = False
            return
        vars_per_platform = expand_selected_brands_for_platforms(selected_brands, platforms)

    all_new_items = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_platform = {
            executor.submit(check_platform, p, vars_per_platform[p], chat_id): p
            for p in platforms if p in PARSERS and vars_per_platform[p]
        }
        for future in as_completed(future_to_platform):
            platform = future_to_platform[future]
            try:
                new_items = future.result()
                all_new_items.extend(new_items)
            except Exception as e:
                logger.error(f"Ошибка при проверке {platform}: {e}")

    send_func = BOT_STATE.get('send_to_telegram')
if send_func and all_new_items:
    for item in all_new_items:
        # Формируем сообщение с HTML-ссылкой
        message = f"🆕 <b>{item['title']}</b>\n💰 {item['price']}\n🏷 {item['source']}\n🔗 <a href='{item['url']}'>Ссылка на товар</a>"
        send_func(message, item.get('img_url'))
        time.sleep(0.5)
    with state_lock:
        BOT_STATE['stats']['total_checks'] += 1
        BOT_STATE['stats']['total_finds'] += len(all_new_items)
        BOT_STATE['last_check'] = time.strftime('%Y-%m-%d %H:%M:%S')
        BOT_STATE['is_checking'] = False

    logger.info(f"✅ Проверка завершена. Найдено новых товаров: {len(all_new_items)}")

def run_scheduler():
    logger.info("Планировщик запущен")
    last_run = 0
    first = True
    
    while not BOT_STATE.get('shutdown', False):
        with state_lock:
            turbo = BOT_STATE.get('turbo_mode', False)
            if turbo:
                interval = 5 * 60
            else:
                interval = BOT_STATE['interval'] * 60
            paused = BOT_STATE['paused']
        
        now = time.time()
        if not paused and not first and (now - last_run) >= interval:
            logger.info(f"⏰ Запуск по расписанию (интервал {interval//60} мин)")
            Thread(target=check_all_marketplaces).start()
            last_run = now
        elif first:
            first = False
            last_run = now
        time.sleep(30)