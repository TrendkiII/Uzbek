import time
import asyncio
from threading import Thread

from config import BOT_STATE, state_lock, logger, stop_event
from brands import detect_brand_from_title
from async_parsers import run_async_search
from database import add_item_with_brand

def run_search(keywords, platforms, chat_id=None, max_concurrent=20):
    if stop_event.is_set():
        logger.info("⏹️ Поиск отменён (stop_event установлен)")
        return []
    
    logger.info(f"🚀 Запуск поиска для {len(keywords)} ключей на {len(platforms)} площадках")
    
    items = run_async_search(keywords, platforms, max_concurrent)
    
    if not items:
        logger.info("📭 Товаров не найдено")
        send_func = BOT_STATE.get('send_to_telegram')
        if send_func and chat_id:
            send_func("📭 Товаров не найдено", chat_id=chat_id)
        return []
    
    new_items = []
    brands_found = set()
    
    for item in items:
        brand = detect_brand_from_title(item.get('title', ''))
        if brand:
            brands_found.add(brand)
        
        if add_item_with_brand(item, brand):
            new_items.append(item)
            with state_lock:
                if item['source'] in BOT_STATE['stats']['platform_stats']:
                    BOT_STATE['stats']['platform_stats'][item['source']]['finds'] += 1
    
    with state_lock:
        BOT_STATE['stats']['total_checks'] += 1
        BOT_STATE['stats']['total_finds'] += len(new_items)
        BOT_STATE['last_check'] = time.strftime('%Y-%m-%d %H:%M:%S')
    
    logger.info(f"📊 Найдены бренды: {', '.join(brands_found) if brands_found else 'НИ ОДНОГО БРЕНДА НЕ ОПРЕДЕЛЕНО!'}")
    
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