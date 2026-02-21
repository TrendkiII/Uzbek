import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

from config import BOT_STATE, state_lock, logger, stop_event
from brands import detect_brand_from_title
from async_parsers import run_async_search
from database import add_item_with_brand
from async_loop import run_coro

# Пул потоков для отправки сообщений (не больше 3 одновременно)
send_executor = ThreadPoolExecutor(max_workers=3)

def send_async_message(send_func, message, photo_url):
    """Отправляет сообщение в отдельном потоке"""
    try:
        send_func(message, photo_url)
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")

def run_search(keywords, platforms, chat_id=None, max_workers=5):
    """
    Основная функция поиска. Запускает асинхронный парсинг (через очередь с воркерами)
    и мгновенно отправляет новые находки.
    """
    if stop_event.is_set():
        logger.info("⏹️ Поиск отменён (stop_event установлен)")
        return []
    
    logger.info(f"🚀 Запуск поиска для {len(keywords)} ключей на {len(platforms)} площадках (воркеров={max_workers})")
    
    # Запускаем асинхронный парсинг в фоновом цикле через run_coro
    # Теперь run_async_search принимает max_workers (количество воркеров)
    items = run_coro(run_async_search(keywords, platforms, max_workers)).result()
    
    if not items:
        logger.info("📭 Товаров не найдено")
        send_func = BOT_STATE.get('send_to_telegram')
        if send_func and chat_id:
            send_func("📭 Товаров не найдено", chat_id=chat_id)
        return []
    
    brands_found = set()
    new_count = 0
    send_func = BOT_STATE.get('send_to_telegram')
    
    for item in items:
        brand = detect_brand_from_title(item.get('title', ''))
        if brand:
            brands_found.add(brand)
        
        if add_item_with_brand(item, brand):
            new_count += 1
            with state_lock:
                if item['source'] in BOT_STATE['stats']['platform_stats']:
                    BOT_STATE['stats']['platform_stats'][item['source']]['finds'] += 1
            
            if send_func:
                message = (
                    f"🆕 <b>{item['title'][:100]}</b>\n"
                    f"💰 {item['price']}\n"
                    f"🏷 {item['source']}\n"
                    f"🔗 <a href='{item['url']}'>Перейти к товару</a>"
                )
                # Отправляем асинхронно через пул потоков
                send_executor.submit(send_async_message, send_func, message, item.get('img_url'))
                # Небольшая задержка, чтобы не перегрузить executor
                time.sleep(0.05)
    
    with state_lock:
        BOT_STATE['stats']['total_checks'] += 1
        BOT_STATE['stats']['total_finds'] += new_count
        BOT_STATE['last_check'] = time.strftime('%Y-%m-%d %H:%M:%S')
    
    logger.info(f"📊 Найдены бренды: {', '.join(brands_found) if brands_found else 'НИ ОДНОГО БРЕНДА НЕ ОПРЕДЕЛЕНО!'}")
    
    # Итоговое сообщение о завершении (опционально)
    if send_func and chat_id:
        send_func(
            f"✅ Поиск завершен!\n"
            f"📊 Найдено товаров: {len(items)}\n"
            f"🆕 Новых: {new_count}\n"
            f"🏷 Брендов: {len(brands_found)}",
            chat_id=chat_id
        )
    
    logger.info(f"✅ Поиск завершен. Новых товаров: {new_count}")
    return items