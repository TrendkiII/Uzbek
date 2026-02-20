import time
import random
import asyncio
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    BOT_STATE, state_lock, logger, MAX_WORKERS, ITEMS_PER_PAGE,
    MIN_DELAY_BETWEEN_REQUESTS, MAX_DELAY_BETWEEN_REQUESTS,
    MIN_DELAY_BETWEEN_BRANDS, MAX_DELAY_BETWEEN_BRANDS,
    stop_event  # добавлено в config позже
)
from brands import (
    expand_selected_brands_for_platforms,
    BRAND_GROUPS,
    detect_brand_from_title
)
from async_parsers import run_async_search
from database import add_item_with_brand

def run_search(keywords, platforms, chat_id=None, max_concurrent=20):
    """
    Основная функция поиска. Запускает асинхронный парсинг, обрабатывает результаты,
    обновляет статистику и отправляет уведомления.
    
    Args:
        keywords: список ключевых слов
        platforms: список платформ
        chat_id: ID чата для отправки уведомлений (опционально)
        max_concurrent: максимальное количество одновременных асинхронных запросов
    """
    # Проверка флага остановки перед началом
    if stop_event.is_set():
        logger.info("⏹️ Поиск отменён (stop_event установлен)")
        return []
    
    logger.info(f"🚀 Запуск поиска для {len(keywords)} ключей на {len(platforms)} площадках")
    
    # Асинхронный поиск
    items = run_async_search(keywords, platforms, max_concurrent)
    
    if not items:
        logger.info("📭 Товаров не найдено")
        send_func = BOT_STATE.get('send_to_telegram')
        if send_func and chat_id:
            send_func("📭 Товаров не найдено", chat_id=chat_id)
        return []
    
    # Обработка результатов
    new_items = []
    brands_found = set()
    
    for item in items:
        # Определяем бренд из названия товара
        brand = detect_brand_from_title(item.get('title', ''))
        if brand:
            brands_found.add(brand)
        
        # Сохраняем в базу
        if add_item_with_brand(item, brand):
            new_items.append(item)
            # Обновляем статистику по платформе
            with state_lock:
                if item['source'] in BOT_STATE['stats']['platform_stats']:
                    BOT_STATE['stats']['platform_stats'][item['source']]['finds'] += 1
    
    # Обновляем общую статистику
    with state_lock:
        BOT_STATE['stats']['total_checks'] += 1
        BOT_STATE['stats']['total_finds'] += len(new_items)
        BOT_STATE['last_check'] = time.strftime('%Y-%m-%d %H:%M:%S')
    
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
            time.sleep(0.5)  # небольшая задержка между отправками
    else:
        if new_items:
            logger.warning("⚠️ Функция отправки не найдена в BOT_STATE")
        else:
            logger.info("📭 Новых товаров не найдено")
    
    # Отправляем итоговое сообщение, если указан chat_id
    if send_func and chat_id:
        send_func(
            f"✅ Поиск завершен!\n"
            f"📊 Найдено товаров: {len(items)}\n"
            f"🆕 Новых: {len(new_items)}\n"
            f"🏷 Брендов: {len(brands_found)}",
            chat_id=chat_id
        )
    
    logger.info(f"✅ Поиск завершен. Новых товаров: {len(new_items)}")
    return new_items

# ==================== СТАРЫЙ МЕТОД (для обратной совместимости) ====================
def check_all_marketplaces(chat_id=None):
    """
    Устаревший метод. Используйте run_search напрямую.
    Сохраняется для совместимости с существующими вызовами.
    """
    with state_lock:
        if BOT_STATE['is_checking'] or BOT_STATE['paused']:
            logger.warning("Проверка уже выполняется или бот на паузе")
            return
        BOT_STATE['is_checking'] = True
        platforms = BOT_STATE['selected_platforms'].copy()
        mode = BOT_STATE['mode']
        selected_brands = BOT_STATE['selected_brands'].copy()
        turbo = BOT_STATE.get('turbo_mode', False)
    
    logger.info(f"🚀 Запуск обычной проверки в режиме {'ТУРБО' if turbo else 'обычном'}")
    
    # Формируем список ключевых слов
    if mode == 'auto':
        # В авторежиме берём все вариации
        all_vars = []
        for group in BRAND_GROUPS:
            for typ in ['latin', 'jp', 'cn', 'universal']:
                if typ in group['variations']:
                    all_vars.extend(group['variations'][typ])
        keywords = list(set(all_vars))
        if not turbo:
            keywords = keywords[:30]  # ограничиваем для обычного режима
    else:
        # Ручной режим
        if not selected_brands:
            logger.warning("Ручной режим, но бренды не выбраны")
            with state_lock:
                BOT_STATE['is_checking'] = False
            return
        # Получаем вариации для первой площадки (можно для всех, но для списка ключей достаточно)
        sample_platform = platforms[0] if platforms else 'Mercari JP'
        keywords = []
        for brand in selected_brands:
            keywords.extend(expand_selected_brands_for_platforms([brand], [sample_platform])[sample_platform])
        keywords = list(set(keywords))
    
    # Запускаем поиск
    result = run_search(keywords, platforms, chat_id, max_concurrent=20 if turbo else 10)
    
    with state_lock:
        BOT_STATE['is_checking'] = False
    
    return result

# ==================== СУПЕР-ТУРБО (теперь это просто alias) ====================
def run_super_turbo_search(keywords, platforms, chat_id=None):
    """
    Запускает супер-турбо поиск (асинхронный с высоким параллелизмом).
    """
    return run_search(keywords, platforms, chat_id, max_concurrent=30)

# ==================== ПЛАНИРОВЩИК ====================
def run_scheduler():
    """
    Планировщик, запускающий проверки по интервалу.
    """
    logger.info("⏰ Планировщик запущен")
    last_run = 0
    first = True
    
    while not BOT_STATE.get('shutdown', False):
        # Проверяем, не установлен ли stop_event (например, при завершении)
        if stop_event.is_set():
            logger.info("⏹️ Планировщик остановлен по сигналу")
            break
        
        with state_lock:
            turbo = BOT_STATE.get('turbo_mode', False)
            if turbo:
                interval = 5 * 60  # 5 минут
            else:
                interval = BOT_STATE['interval'] * 60
            paused = BOT_STATE['paused']
        
        now = time.time()
        if not paused and not first and (now - last_run) >= interval:
            logger.info(f"⏰ Запуск по расписанию (интервал {interval//60} мин)")
            # Запускаем в отдельном потоке, чтобы не блокировать планировщик
            Thread(target=check_all_marketplaces).start()
            last_run = now
        elif first:
            first = False
            last_run = now
        time.sleep(30)