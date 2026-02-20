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

def process_new_items(items, platform, brand_main=None):
    """
    Обрабатывает список товаров, сохраняет новые и возвращает их
    Теперь сохраняет с привязкой к основному бренду
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
    Теперь определяет основной бренд для каждой вариации
    """
    parser = PARSERS.get(platform)
    if not parser:
        logger.warning(f"Нет парсера для {platform}")
        return []
    
    platform_new_items = []
    turbo = BOT_STATE.get('turbo_mode', False)
    request_count = 0
    
    for var in variations:
        # Получаем основной бренд для этой вариации (НОВАЯ ФУНКЦИЯ)
        brand_main = get_main_brand_by_variation(var)
        if brand_main:
            logger.info(f"🔍 Вариация '{var}' соответствует бренду '{brand_main}'")
        
        # Проверяем флаг остановки
        with state_lock:
            if BOT_STATE.get('stop_requested', False):
                logger.info(f"⏹️ Остановка проверки на платформе {platform} по запросу пользователя")
                # Сбрасываем флаг, чтобы следующая проверка не была остановлена сразу
                with state_lock:
                    BOT_STATE['stop_requested'] = False
                break

        request_count += 1
        logger.info(f"[{platform}] Поиск {request_count}/{len(variations)}: {var}")
        
        items = parser(var)
        
        if items:
            # Передаём brand_main в process_new_items
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
    with state_lock:
        # Сбрасываем флаг остановки перед началом проверки
        BOT_STATE['stop_requested'] = False
        if BOT_STATE['is_checking'] or BOT_STATE['paused']:
            logger.warning("Проверка уже выполняется или бот на паузе")
            return
        BOT_STATE['is_checking'] = True
        platforms = BOT_STATE['selected_platforms'].copy()
        mode = BOT_STATE['mode']
        selected_brands = BOT_STATE['selected_brands'].copy()
        turbo = BOT_STATE.get('turbo_mode', False)

# ВРЕМЕННАЯ ЗАЩИТА: если есть выбранные бренды, режим должен быть manual
if selected_brands and mode == 'auto':
    mode = 'manual'
    logger.info(f"🔄 Автоматически переключено в manual для брендов: {selected_brands}")

    logger.info(f"🚀 Запуск проверки в режиме {'ТУРБО' if turbo else 'обычном'}")

    # Логируем статистику прокси перед началом
    proxy_stats = get_proxy_stats()
    logger.info(f"📊 Прокси в пуле: {proxy_stats['total']}, рабочих: {proxy_stats['good']}")

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

    # Отправка найденных товаров
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

    # Обновляем статистику
    with state_lock:
        BOT_STATE['stats']['total_checks'] += 1
        BOT_STATE['stats']['total_finds'] += len(all_new_items)
        BOT_STATE['last_check'] = time.strftime('%Y-%m-%d %H:%M:%S')
        BOT_STATE['is_checking'] = False
        # Сбрасываем флаг остановки (на случай, если проверка завершилась без остановки)
        BOT_STATE['stop_requested'] = False

    logger.info(f"✅ Проверка завершена. Найдено новых товаров: {len(all_new_items)}")
    
    # Финальная статистика прокси
    proxy_stats = get_proxy_stats()
    logger.info(f"📊 Итоговая статистика прокси: всего {proxy_stats['total']}, рабочих {proxy_stats['good']}")

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
                interval = 5 * 60  # 5 минут в турбо-режиме
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