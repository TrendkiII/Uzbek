import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import quote
from config import ITEMS_PER_PAGE, logger
from utils import (
    generate_item_id, make_full_url, get_next_user_agent,
    get_next_proxy_async, mark_proxy_bad_str
)
from playwright_manager import fetch_html_playwright  # заменили playwright_fallback

# ==================== Быстрый асинхронный запрос с прокси ====================
async def fetch_html(session, url, semaphore, timeout=15, retries=3):
    # ... (без изменений, как в предыдущем async_parsers)
    async with semaphore:
        headers = {
            'User-Agent': get_next_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        for attempt in range(retries):
            proxy = await get_next_proxy_async()
            try:
                async with session.get(url, headers=headers, proxy=proxy, timeout=timeout, ssl=False) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status in [403, 404]:
                        logger.warning(f"🚫 {response.status} для {url[:100]}...")
                        return None
                    else:
                        logger.warning(f"🌐 HTTP {response.status} для {url[:100]}...")
            except asyncio.TimeoutError:
                logger.warning(f"⏰ Таймаут (попытка {attempt+1}) для {url[:100]}...")
            except aiohttp.ClientProxyConnectionError as e:
                logger.warning(f"🔌 Ошибка прокси {proxy} (попытка {attempt+1}): {e}")
                if proxy:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, mark_proxy_bad_str, proxy)
            except aiohttp.ClientConnectorError as e:
                logger.warning(f"🔌 Ошибка подключения (попытка {attempt+1}): {e}")
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки {url[:100]}: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
        return None

# ==================== Гибридная загрузка: сначала быстрый fetch, при неудаче — Playwright ====================
async def fetch_with_fallback(session, url, semaphore, expected_selector=None, use_playwright=True):
    html = await fetch_html(session, url, semaphore)
    if html:
        if expected_selector:
            soup = BeautifulSoup(html, 'lxml')
            if soup.select_one(expected_selector):
                return html
            else:
                logger.warning(f"⚠️ Быстрый запрос успешен, но селектор '{expected_selector}' не найден. Пробую Playwright.")
        else:
            return html

    if use_playwright:
        logger.info(f"🔄 Fallback to Playwright for {url[:100]}...")
        html = await fetch_html_playwright(url, expected_selector=expected_selector)
        return html
    return None

# ==================== Вспомогательная функция для извлечения данных из карточки ====================
def extract_item_from_card(card, source, base_url, title_sel, price_sel, link_sel='a', img_sel='img'):
    # ... (без изменений)
    try:
        title_elem = card.select_one(title_sel)
        price_elem = card.select_one(price_sel)
        link_elem = card.select_one(link_sel)
        img_elem = card.select_one(img_sel) if img_sel else None

        if not title_elem or not link_elem:
            return None

        title = title_elem.text.strip()
        price = price_elem.text.strip() if price_elem else 'Цена не указана'

        img_url = None
        if img_elem:
            img_url = img_elem.get('src')
            if img_url and img_url.startswith('//'):
                img_url = 'https:' + img_url

        href = link_elem.get('href')
        full_url = make_full_url(base_url, href)

        return {
            'title': title[:100],
            'price': price[:50],
            'url': full_url,
            'img_url': img_url,
            'source': source
        }
    except Exception as e:
        logger.debug(f"Ошибка парсинга карточки {source}: {e}")
        return None

# ==================== Парсеры (каждый использует fetch_with_fallback) ====================
async def parse_mercari_async(session, keyword, semaphore):
    items = []
    url = f"https://jp.mercari.com/search?keyword={quote(keyword)}&order=desc&sort=created_time"
    html = await fetch_with_fallback(session, url, semaphore, expected_selector='[data-testid="item-cell"]')
    if not html:
        return items
    try:
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('[data-testid="item-cell"]')[:ITEMS_PER_PAGE]
        for card in cards:
            item_data = extract_item_from_card(
                card,
                source='Mercari JP',
                base_url='https://jp.mercari.com',
                title_sel='[data-testid="thumbnail-title"]',
                price_sel='[data-testid="price"]',
                link_sel='a',
                img_sel='img'
            )
            if item_data:
                item_data['id'] = generate_item_id(item_data)
                items.append(item_data)
    except Exception as e:
        logger.error(f"Ошибка парсинга Mercari для {keyword}: {e}")
    return items

# Аналогично для остальных площадок (Rakuma, Yahoo Flea, Yahoo Auction, Yahoo Shopping, Rakuten Mall, eBay, 2nd Street)
# (здесь нужно скопировать остальные функции из предыдущей версии async_parsers, заменив fetch_html на fetch_with_fallback)

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

# ==================== Основная функция поиска ====================
async def search_all_async(keywords, platforms, max_concurrent=20):
    semaphore = asyncio.Semaphore(max_concurrent)
    connector = aiohttp.TCPConnector(limit=100, limit_per_host=10, ttl_dns_cache=300, ssl=False)
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        for platform in platforms:
            if platform in ASYNC_PARSERS:
                parser = ASYNC_PARSERS[platform]
                for keyword in keywords:
                    tasks.append(parser(session, keyword, semaphore))
        
        logger.info(f"🚀 Запущено {len(tasks)} асинхронных задач")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_items = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Ошибка в асинхронной задаче: {result}")
            elif isinstance(result, list):
                all_items.extend(result)
        
        logger.info(f"✅ Асинхронный поиск завершен, найдено {len(all_items)} товаров")
        return all_items

# ==================== Функция для запуска из синхронного кода ====================
def run_async_search(keywords, platforms, max_concurrent=20):
    # Создаём новый цикл или используем существующий? Лучше использовать общий.
    # Импортируем run_coro из async_loop, чтобы выполнить в фоновом цикле.
    from async_loop import run_coro
    future = run_coro(search_all_async(keywords, platforms, max_concurrent))
    return future.result()  # ждём результат