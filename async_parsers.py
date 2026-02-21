import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import quote
from config import ITEMS_PER_PAGE, logger
from utils import (
    generate_item_id, make_full_url, get_next_user_agent,
    get_next_proxy_async, mark_proxy_bad_str
)
from playwright_manager import fetch_html_playwright

try:
    import brotli
except ImportError:
    logger.warning("Brotli not installed, some sites may fail. Run: pip install brotli")

# Глобальный семафор для ограничения общего числа параллельных запросов (HTTP + Playwright)
GLOBAL_SEMAPHORE = asyncio.Semaphore(10)  # максимум 10 одновременных запросов всего

# Отдельный семафор для Playwright (чтобы не перегружать браузер)
PLAYWRIGHT_SEMAPHORE = asyncio.Semaphore(2)  # не больше 2 страниц одновременно

async def fetch_html(session, url):
    # ... (без изменений, см. предыдущие версии)
    pass

async def fetch_with_fallback(session, url, expected_selector=None, use_playwright=True):
    # ... (без изменений)
    pass

def extract_item_from_card(card, source, base_url, title_sel, price_sel, link_sel='a', img_sel='img'):
    # ... (без изменений)
    pass

async def parse_mercari_async(session, keyword):
    # ... (без изменений)
    pass

# ... остальные парсеры (без изменений)

# ==================== Словарь парсеров ====================
ASYNC_PARSERS = {
    'Mercari JP': parse_mercari_async,
    'Rakuten Rakuma': parse_rakuma_async,
    'Yahoo Flea': parse_yahoo_flea_async,
    'Yahoo Auction': parse_yahoo_auction_async,
    'Yahoo Shopping': parse_yahoo_shopping_async,
    'Rakuten Mall': parse_rakuten_mall_async,
    'eBay': parse_ebay_async,
    '2nd Street JP': parse_2ndstreet_async,
}

# ==================== Функция с очередью и воркерами ====================
async def worker(queue, session, results):
    while True:
        task = await queue.get()
        if task is None:
            break
        platform, keyword = task
        parser = ASYNC_PARSERS.get(platform)
        if parser:
            try:
                items = await parser(session, keyword)
                results.extend(items)
            except Exception as e:
                logger.error(f"Ошибка при обработке {platform}/{keyword}: {e}")
        queue.task_done()

async def search_all_async(keywords, platforms, max_workers=5):
    queue = asyncio.Queue()
    results = []

    for platform in platforms:
        if platform not in ASYNC_PARSERS:
            continue
        for keyword in keywords:
            await queue.put((platform, keyword))

    connector = aiohttp.TCPConnector(limit=100, limit_per_host=5, ttl_dns_cache=300, ssl=False)
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        workers = [asyncio.create_task(worker(queue, session, results)) for _ in range(max_workers)]
        await queue.join()
        for _ in workers:
            await queue.put(None)
        await asyncio.gather(*workers)

    logger.info(f"✅ Асинхронный поиск завершен, найдено {len(results)} товаров")
    return results

# ==================== Функция для запуска из синхронного кода ====================
def run_async_search(keywords, platforms, max_workers=5):
    from async_loop import run_coro
    future = run_coro(search_all_async(keywords, platforms, max_workers))
    return future.result()  # возвращает результат синхронно