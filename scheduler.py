import time
import random
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import (
    BOT_STATE, state_lock, logger, MAX_WORKERS, ITEMS_PER_PAGE,
    MIN_DELAY_BETWEEN_REQUESTS, MAX_DELAY_BETWEEN_REQUESTS,
    MIN_DELAY_BETWEEN_BRANDS, MAX_DELAY_BETWEEN_BRANDS
)
from brands import expand_selected_brands_for_platforms, BRAND_GROUPS, get_main_brand_by_variation
from parsers import PARSERS
from database import add_item_with_brand
from utils import (
    generate_item_id, human_delay, brand_delay,
    get_proxy_stats
)
from async_parsers import run_async_search

def process_new_items(items, platform, brand_main=None):
    """
    Обрабатывает список товаров, сохраняет новые и возвращает их
    """
    if not items:
        return []
    
    # Добавляем ID каждому товару
    for item in items:
        if 'id' not in item:
            item['id'] = generate_item_id(item)
    
    new_items = []
    
    for item in items:
        # Добавляем товар в базу с указанием основного бренда
        if add_item_with_brand(item, brand_main):
            new_items.append(item)
            with state_lock:
                if platform in BOT_STATE['stats']['platform_stats']:
                    BOT_STATE['stats']['platform_stats'][platform]['finds'] += 1
    
    return new_items

def check_platform(platform, variations, chat_id=None):
    """
    Парсит одну платформу по списку вариаций с маскировкой.
    """
    parser = PARSERS.get(platform)
    if not parser:
        logger.warning(f"Нет парсера для {platform}")
        return []
    
    platform_new_items = []
    turbo = BOT_STATE.get('turbo_mode', False)
    request_count = 0
    
    for var in variations:
        # Получаем основной бренд для этой вариации
        brand_main = get_main_brand_by_variation(var)
        if brand_main:
            logger.info(f"🔍 Вариация '{var}' соответствует бренду '{brand_main}'")
        
        # Проверяем флаг остановки
        with state_lock:
            if BOT_STATE.get('stop_requested', False):
                logger.info(f"⏹️ Остановка проверки на платформе {platform} по запросу пользователя")
                with state_lock:
                    BOT_STATE['stop_requested'] = False
                break

        request_count += 1
        logger.info(f"[{platform}] Поиск {request_count}/{len(variations)}: {var}")
        
        items = parser(var)
        
        if items:
            new = process_new_items(items, platform, brand_main)
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
    """
    Обычная проверка (синхронная)
    """
    with state_lock:
        BOT_STATE['stop_requested'] = False
        if BOT_STATE['is_checking'] or BOT_STATE['paused']:
            logger.warning("Проверка уже выполняется или бот на паузе")
            return
        BOT_STATE['is_checking'] = True
        platforms = BOT_STATE['selected_platforms'].copy()
        mode = BOT_STATE['mode']
        selected_brands = BOT_STATE['selected_brands'].copy()
        turbo = BOT_STATE.get('turbo_mode', False)

    if selected_brands and mode == 'auto':
        mode = 'manual'
        logger.info(f"🔄 Автоматически переключено в manual для брендов: {selected_brands}")

    logger.info(f"🚀 Запуск обычной проверки в режиме {'ТУРБО' if turbo else 'обычном'}")

    proxy_stats = get_proxy_stats()
    logger.info(f"📊 Прокси в пуле: {proxy_stats['total']}, рабочих: {proxy_stats['good']}")

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
                logger.error(f"❌ Ошибка при проверке {platform}: {e}")

    send_func = BOT_STATE.get('send_to_telegram')
    if send_func and all_new_items:
        logger.info(f"📨 Отправляю {len(all_new_items)} новых товаров")
        for item in all_new_items:
            message = (
                f"🆕 <b>{item['title'][:100]}</b>\n"
                f"💰 {item['price']}\n"
                f"🏷 {item['source']}\n"
                f"🔗 <a href='{item['url']}'>Перейти к товару</a>"
            )
            send_func(message, item.get('img_url'))
            time.sleep(0.5)
    else:
        if all_new_items:
            logger.warning("⚠️ Функция отправки не найдена в BOT_STATE")
        else:
            logger.info("📭 Новых товаров не найдено")

    with state_lock:
        BOT_STATE['stats']['total_checks'] += 1
        BOT_STATE['stats']['total_finds'] += len(all_new_items)
        BOT_STATE['last_check'] = time.strftime('%Y-%m-%d %H:%M:%S')
        BOT_STATE['is_checking'] = False
        BOT_STATE['stop_requested'] = False

    logger.info(f"✅ Обычная проверка завершена. Найдено новых товаров: {len(all_new_items)}")
    
    proxy_stats = get_proxy_stats()
    logger.info(f"📊 Итоговая статистика прокси: всего {proxy_stats['total']}, рабочих {proxy_stats['good']}")

# ==================== НОВАЯ ФУНКЦИЯ ДЛЯ СУПЕР-ТУРБО С ОТЛАДКОЙ ====================
def run_super_turbo_search(keywords, platforms, chat_id=None):
    """
    Запускает супер-быстрый асинхронный поиск с отладкой
    """
    logger.info(f"⚡ Запуск супер-турбо поиска для {len(keywords)} ключей на {len(platforms)} площадках")
    
    # Асинхронный поиск
    items = run_async_search(keywords, platforms, max_concurrent=30)
    
    if not items:
        logger.info("📭 Товаров не найдено")
        send_func = BOT_STATE.get('send_to_telegram')
        if send_func:
            send_func("📭 Товаров не найдено", chat_id=chat_id)
        return []
    
    # ========== ОТЛАДКА: смотрим первые 10 товаров ==========
    logger.info(f"📊 Получено {len(items)} товаров. Анализируем первые 10:")
    for i, item in enumerate(items[:10]):
        brand_main = get_main_brand_by_variation(item.get('title', ''))
        logger.info(f"🔍 Товар {i+1}:")
        logger.info(f"   📝 Название: {item.get('title', '')[:100]}")
        logger.info(f"   🏷 Определенный бренд: {brand_main}")
        logger.info(f"   🔗 Источник: {item.get('source', '')}")
        logger.info(f"   💰 Цена: {item.get('price', '')}")
        logger.info(f"   🆔 ID: {item.get('id', 'НЕТ ID!')}")
    # ======================================================
    
    # Обработка результатов
    new_items = []
    brands_found = set()
    
    for item in items:
        # Определяем бренд из названия
        brand_main = get_main_brand_by_variation(item.get('title', ''))
        if brand_main:
            brands_found.add(brand_main)
        
        # Сохраняем в базу
        if add_item_with_brand(item, brand_main):
            new_items.append(item)
            with state_lock:
                if item['source'] in BOT_STATE['stats']['platform_stats']:
                    BOT_STATE['stats']['platform_stats'][item['source']]['finds'] += 1
    
    # Логируем статистику по брендам
    logger.info(f"📊 Найдены бренды: {', '.join(brands_found) if brands_found else 'НИ ОДНОГО БРЕНДА НЕ ОПРЕДЕЛЕНО!'}")
    
    # Отправка уведомлений
    send_func = BOT_STATE.get('send_to_telegram')
    if send_func and new_items:
        logger.info(f"📨 Отправляю {len(new_items)} новых товаров")
        for item in new_items:
            message = (
                f"🆕 <b>{item['title'][:100]}</b>\n"
                f"💰 {item['price']}\n"
                f"🏷 {item['source']}\n"
                f"🔗 <a href='{item['url']}'>Перейти к товару</a>"
            )
            send_func(message, item.get('img_url'))
            time.sleep(0.5)
    else:
        if new_items:
            logger.warning("⚠️ Функция отправки не найдена в BOT_STATE")
        else:
            logger.info("📭 Новых товаров не найдено")
    
    logger.info(f"✅ Супер-турбо поиск завершен. Новых товаров: {len(new_items)}")
    logger.info(f"📊 Всего обработано товаров: {len(items)}")
    
    # Отправляем итоговое сообщение
    if send_func:
        send_func(
            f"⚡ Супер-турбо поиск завершен!\n"
            f"📊 Найдено товаров: {len(items)}\n"
            f"🆕 Новых: {len(new_items)}\n"
            f"🏷 Брендов: {len(brands_found)}",
            chat_id=chat_id
        )
    
    return new_items

def run_scheduler():
    """
    Планировщик, запускающий проверки по интервалу.
    """
    logger.info("⏰ Планировщик запущен")
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