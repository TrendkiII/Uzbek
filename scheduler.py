import time
import random
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import BOT_STATE, state_lock, logger, MAX_WORKERS, ITEMS_PER_PAGE
from brands import expand_selected_brands_for_platforms, BRAND_GROUPS
from parsers import PARSERS
from database import add_item
from utils import generate_item_id

def process_new_items(items, platform):
    """Обрабатывает список товаров, сохраняет новые и возвращает их"""
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
    """Парсит одну платформу по списку вариаций."""
    parser = PARSERS.get(platform)
    if not parser:
        logger.warning(f"Нет парсера для {platform}")
        return []
    
    platform_new_items = []
    turbo = BOT_STATE.get('turbo_mode', False)
    
    for var in variations:
        logger.info(f"[{platform}] Поиск: {var}")
        items = parser(var)
        if items:
            new = process_new_items(items, platform)
            platform_new_items.extend(new)
            logger.info(f"[{platform}] Найдено {len(items)} товаров, новых {len(new)}")
        
        # В турбо-режиме почти нет задержки
        if turbo:
            time.sleep(random.uniform(0.5, 1))
        else:
            time.sleep(random.uniform(1, 2))
    
    return platform_new_items

def check_all_marketplaces(chat_id=None):
    """Основная функция проверки всех выбранных площадок."""
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

    # Формируем список вариаций
    if mode == 'auto':
        all_vars = []
        for group in BRAND_GROUPS:
            for typ in ['latin', 'jp', 'cn', 'universal']:
                if typ in group['variations']:
                    all_vars.extend(group['variations'][typ])
        all_vars = list(set(all_vars))
        random.shuffle(all_vars)
        # В турбо-режиме проверяем больше вариаций
        vars_per_platform = {p: all_vars[:30] if turbo else all_vars[:20] for p in platforms}
    else:
        if not selected_brands:
            logger.warning("Ручной режим, но бренды не выбраны")
            with state_lock:
                BOT_STATE['is_checking'] = False
            return
        vars_per_platform = expand_selected_brands_for_platforms(selected_brands, platforms)

    # Параллельная проверка
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

    # Отправляем уведомления
    send_func = BOT_STATE.get('send_to_telegram')
    if send_func and all_new_items:
        for item in all_new_items:
            send_func(item)

    # Обновляем статистику
    with state_lock:
        BOT_STATE['stats']['total_checks'] += 1
        BOT_STATE['stats']['total_finds'] += len(all_new_items)
        BOT_STATE['last_check'] = time.strftime('%Y-%m-%d %H:%M:%S')
        BOT_STATE['is_checking'] = False

    logger.info(f"✅ Проверка завершена. Найдено новых товаров: {len(all_new_items)}")

def run_scheduler():
    """Планировщик, запускающий проверки по интервалу."""
    logger.info("Планировщик запущен")
    last_run = 0
    first = True
    
    while not BOT_STATE.get('shutdown', False):
        with state_lock:
            turbo = BOT_STATE.get('turbo_mode', False)
            if turbo:
                interval = 5 * 60  # 5 минут в турбо-режиме
            else:
                interval = BOT_STATE['interval'] * 60
            paused = BOT_STATE['paused']
        
        now = time.time()
        if not paused and not first and (now - last_run) >= interval:
            logger.info(f"Запуск по расписанию (интервал {interval//60} мин)")
            Thread(target=check_all_marketplaces).start()
            last_run = now
        elif first:
            first = False
            last_run = now
        time.sleep(30)