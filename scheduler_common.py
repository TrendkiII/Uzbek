import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

from config import BOT_STATE, state_lock, logger, stop_event
from brands import detect_brand_from_title
from async_parsers import run_async_search
from database import add_item_with_brand
from async_loop import run_coro  # больше не используется здесь, но оставим для совместимости

# Пул потоков для отправки сообщений (не больше 3 одновременно)
send_executor = ThreadPoolExecutor(max_workers=3)

def send_async_message(send_func, message, photo_url):
    """Отправляет сообщение в отдельном потоке"""
    try:
        send_func(message, photo_url)
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")

# Флаг для предотвращения повторного запуска поиска
_search_in_progress = False
_search_lock = asyncio.Lock()  # Блокировка для асинхронного доступа (пока не используется)

def run_search(keywords, platforms, chat_id=None, max_workers=5):
    """
    Основная функция поиска. Запускает асинхронный парсинг (через очередь с воркерами)
    и мгновенно отправляет новые находки.
    """
    global _search_in_progress
    
    if stop_event.is_set():
        logger.info("⏹️ Поиск отменён (stop_event установлен)")
        return []
    
    # Проверяем, не выполняется ли уже поиск
    if _search_in_progress:
        logger.warning("⚠️ Поиск уже выполняется, пропускаю новый запуск")
        send_func = BOT_STATE.get('send_to_telegram')
        if send_func and chat_id:
            send_func("⚠️ Поиск уже выполняется, подождите завершения", chat_id=chat_id)
        return []
    
    _search_in_progress = True
    try:
        logger.info(f"🚀 Запуск поиска для {len(keywords)} ключей на {len(platforms)} площадках (воркеров={max_workers})")
        
        # run_async_search уже является синхронной функцией, которая сама запускает асинхронный код через run_coro
        items = run_async_search(keywords, platforms, max_workers)
        
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
                    time.sleep(0.05)  # небольшая задержка между отправками
        
        with state_lock:
            BOT_STATE['stats']['total_checks'] += 1
            BOT_STATE['stats']['total_finds'] += new_count
            BOT_STATE['last_check'] = time.strftime('%Y-%m-%d %H:%M:%S')
        
        logger.info(f"📊 Найдены бренды: {', '.join(brands_found) if brands_found else 'НИ ОДНОГО БРЕНДА НЕ ОПРЕДЕЛЕНО!'}")
        
        # Итоговое сообщение о завершении
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
    finally:
        _search_in_progress = False
        logger.debug("🔓 Поиск разблокирован")